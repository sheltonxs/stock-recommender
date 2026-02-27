"""盘后定时任务: 采集 -> 计算 -> 评分 -> 写入 -> 回测"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.cache import is_trading_time
from app.db import get_session
from app.collectors.market import MarketCollector
from app.collectors.fundamental import FundamentalCollector
from app.collectors.money_flow import MoneyFlowCollector
from app.collectors.sentiment import SentimentCollector
from app.analyzers.technical import TechnicalAnalyzer
from app.analyzers.fundamental import FundamentalAnalyzer
from app.analyzers.money_flow import MoneyFlowAnalyzer
from app.analyzers.sentiment import SentimentAnalyzer
from app.analyzers.scorer import CompositeScorer
from app.models.database import (
    StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation, RecommendationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline 并发控制
# ---------------------------------------------------------------------------

_pipeline_lock = threading.Lock()
_pipeline_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_error": None,
    "phase": None,
    "progress": "",
    "data_source": None,
}


def get_pipeline_status() -> dict:
    """返回 pipeline 当前状态（线程安全）"""
    return dict(_pipeline_status)


def run_daily_pipeline():
    """每日盘后完整流水线（带并发锁 + 自动重试）"""
    if not _pipeline_lock.acquire(blocking=False):
        logger.warning("Pipeline 已在运行中，跳过本次触发")
        return

    try:
        _pipeline_status["running"] = True
        _pipeline_status["started_at"] = datetime.now().isoformat()
        _pipeline_status["last_error"] = None
        _pipeline_status["phase"] = "starting"

        _run_pipeline_inner()

        _pipeline_status["last_error"] = None
        _pipeline_status["phase"] = "completed"
        _pipeline_status["retry_count"] = 0
    except Exception as e:
        _pipeline_status["last_error"] = str(e)
        _pipeline_status["phase"] = "failed"
        logger.error(f"流水线异常: {e}")

        # 自动重试
        retry_count = _pipeline_status.get("retry_count", 0)
        if retry_count < settings.pipeline_max_retries:
            _pipeline_status["retry_count"] = retry_count + 1
            delay_min = settings.pipeline_retry_delay_minutes
            retry_time = datetime.now() + timedelta(minutes=delay_min)
            logger.info(f"流水线失败，{delay_min}分钟后第{retry_count + 1}次重试 ({retry_time:%H:%M})")
            _schedule_retry(retry_time)
        else:
            logger.error(f"流水线已重试{retry_count}次仍失败，放弃")
    finally:
        _pipeline_status["running"] = False
        _pipeline_status["finished_at"] = datetime.now().isoformat()
        _pipeline_lock.release()


def _schedule_retry(run_date):
    """安排一次性重试任务（使用 threading.Timer）"""
    delay_seconds = (run_date - datetime.now()).total_seconds()
    if delay_seconds < 0:
        delay_seconds = 60
    timer = threading.Timer(delay_seconds, run_daily_pipeline)
    timer.daemon = True
    timer.start()
    logger.info(f"已安排 {delay_seconds:.0f} 秒后重试")


# ---------------------------------------------------------------------------
# Pipeline 核心逻辑
# ---------------------------------------------------------------------------

def _run_pipeline_inner():
    """实际的 Pipeline 逻辑"""
    logger.info("===== 每日流水线启动 =====")
    session = get_session()

    # A1: 夜间模式检测
    nighttime = not is_trading_time()
    if nighttime:
        logger.info("夜间模式: 跳过实时快照，优先使用缓存/备用数据源")

    try:
        # --- Phase 1: 快照 + 过滤 ---
        _pipeline_status["phase"] = "snapshot"
        logger.info("[1/4] 获取全A快照并过滤...")
        mc = MarketCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)

        try:
            if nighttime:
                # 夜间模式: 跳过 push2，直接走 Tier2/Tier3
                snapshot_df = mc._collect_snapshot_night()
                if snapshot_df is None or snapshot_df.empty:
                    snapshot_df = mc._load_snapshot_cache()
                    logger.info("夜间模式: 使用文件缓存快照")
                else:
                    logger.info(f"夜间模式: comment_em 快照 {len(snapshot_df)} 条")
            else:
                snapshot_df = mc.collect_snapshot()
        except Exception as e:
            logger.error(f"快照获取失败: {e}")
            snapshot_df = pd.DataFrame()

        pool = _filter_stock_pool(snapshot_df)

        # 快速预排序: 成交额大、涨幅接近2%的优先进入采集池
        pool.sort(key=lambda r: (
            -min(r.get("amount", 0), 1e10),
            abs(r.get("change_pct", 0) - 2),
        ))

        # 始终截断到 pool_multiplier 倍 (默认200只)
        max_pool = settings.stock_pool_size * settings.pool_multiplier
        if len(pool) > max_pool:
            logger.info(f"股票池 {len(pool)} 只，截断至 {max_pool}")
            pool = pool[:max_pool]

        stock_list = [(r["code"], r["name"]) for r in pool]
        logger.info(f"过滤后股票池: {len(stock_list)} 只")
        _pipeline_status["progress"] = f"股票池 {len(stock_list)} 只"

        # Tier 4 降级: 快照为空时从数据库历史数据构建股票池
        if not stock_list:
            logger.warning("快照股票池为空，尝试从数据库构建...")
            stock_list = _build_pool_from_db(session)
            if stock_list:
                _pipeline_status["data_source"] = "database"
                _pipeline_status["progress"] = f"股票池 {len(stock_list)} 只 (数据库降级)"
                logger.info(f"数据库降级: 获得 {len(stock_list)} 只股票")
            else:
                logger.warning("数据库也无可用数据，跳过")
                return
        else:
            _pipeline_status["data_source"] = "night_snapshot" if nighttime else "snapshot"

        # --- Phase 2: 数据采集（各采集器独立容错） ---
        _pipeline_status["phase"] = "collecting"
        logger.info("[2/4] 数据采集...")

        fc = FundamentalCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)

        if nighttime:
            # 夜间: 东方财富所有API不稳定，跳过全部采集，使用历史数据评分
            logger.info("夜间模式: 跳过数据采集(东方财富API夜间不稳定)，使用历史数据评分")
            sentiment_data = {"sector_flow": pd.DataFrame(), "boards": pd.DataFrame(),
                              "zt_pool": pd.DataFrame(), "north_flow": pd.DataFrame()}
        else:
            # 盘中/盘后: 运行所有采集器
            # K线采集
            try:
                mc.collect(stock_list, session)
            except Exception as e:
                logger.error(f"K线采集异常(继续执行): {e}")

            # 基本面采集
            try:
                fc.collect(stock_list, session)
            except Exception as e:
                logger.error(f"基本面采集异常(继续执行): {e}")

            # 资金流采集
            mfc = MoneyFlowCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
            try:
                mfc.collect(stock_list, session)
            except Exception as e:
                logger.error(f"资金流采集异常(继续执行): {e}")

            # 情绪数据采集
            sc = SentimentCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
            sentiment_data = {"sector_flow": pd.DataFrame(), "boards": pd.DataFrame(),
                              "zt_pool": pd.DataFrame(), "north_flow": pd.DataFrame()}
            try:
                sentiment_data = sc.collect()
            except Exception as e:
                logger.error(f"情绪数据采集异常(使用空数据继续): {e}")

            # Enrich fundamentals with spot data
            if snapshot_df is not None and not snapshot_df.empty:
                for code, name in stock_list:
                    try:
                        spot_row = snapshot_df[snapshot_df["代码"] == code]
                        if not spot_row.empty:
                            fc.enrich_from_spot(code, spot_row.iloc[0].to_dict(), session)
                    except Exception:
                        pass

            # PE/PB 补全 (仅对缺失记录)
            try:
                fc.enrich_pe_pb(stock_list, session)
            except Exception as e:
                logger.error(f"PE/PB补全异常(继续执行): {e}")

        # --- Phase 3: 评分 ---
        _pipeline_status["phase"] = "scoring"
        logger.info("[3/4] 评分计算...")
        from app.collectors.industry import get_industry_map
        try:
            industry_map = get_industry_map()
        except Exception as e:
            logger.warning(f"行业映射加载失败(使用空映射继续): {e}")
            industry_map = {}
        logger.info(f"行业映射: {len(industry_map)} 只")
        tech_analyzer = TechnicalAnalyzer()
        fund_analyzer = FundamentalAnalyzer()
        money_analyzer = MoneyFlowAnalyzer()
        sent_analyzer = SentimentAnalyzer()
        scorer = CompositeScorer()

        trade_date = datetime.now().date()

        # --- B5: 批量预加载数据 ---
        all_codes = [code for code, _ in stock_list]

        # 批量加载 K 线
        kline_all = session.query(StockDaily).filter(
            StockDaily.stock_code.in_(all_codes)
        ).order_by(StockDaily.stock_code, StockDaily.trade_date).all()
        kline_map = defaultdict(list)
        for r in kline_all:
            kline_map[r.stock_code].append(r)

        # 批量加载最新基本面 (每只股票取最新一条)
        fund_all = session.query(StockFundamental).filter(
            StockFundamental.stock_code.in_(all_codes)
        ).order_by(StockFundamental.report_date.desc()).all()
        fund_map = {}
        for r in fund_all:
            if r.stock_code not in fund_map:
                fund_map[r.stock_code] = r

        # 批量加载资金流（最近 10 天）
        from sqlalchemy import func
        ten_days_ago = trade_date - timedelta(days=15)
        mf_all = session.query(StockMoneyFlow).filter(
            StockMoneyFlow.stock_code.in_(all_codes),
            StockMoneyFlow.trade_date >= ten_days_ago,
        ).order_by(StockMoneyFlow.stock_code, StockMoneyFlow.trade_date).all()
        mf_map = defaultdict(list)
        for r in mf_all:
            mf_map[r.stock_code].append(r)

        logger.info(f"批量加载完成: K线{len(kline_all)}条, 基本面{len(fund_map)}只, 资金流{len(mf_all)}条")

        # --- B1: 构建行业平均 PE 映射 ---
        industry_pe_sums = defaultdict(lambda: [0.0, 0])  # {industry: [sum_pe, count]}
        for code in all_codes:
            ind = industry_map.get(code, "")
            if not ind:
                continue
            fund_row = fund_map.get(code)
            if fund_row and fund_row.pe_ttm and 0 < fund_row.pe_ttm < 300:
                industry_pe_sums[ind][0] += fund_row.pe_ttm
                industry_pe_sums[ind][1] += 1
        industry_pe_map = {k: v[0] / v[1] for k, v in industry_pe_sums.items() if v[1] >= 3}

        # 硬编码行业 PE 基准回退表
        _FALLBACK_PE = {
            "银行": 6, "保险": 10, "证券": 20, "房地产": 8,
            "白酒": 35, "医药": 30, "半导体": 50, "软件": 45,
            "光伏": 25, "新能源": 35, "汽车": 20, "钢铁": 10,
            "煤炭": 8, "电力": 15, "化工": 15, "家电": 15,
        }
        logger.info(f"行业PE映射: {len(industry_pe_map)} 个行业有动态PE")

        results = []
        scored_count = 0

        for code, name in stock_list:
            try:
                # B5: 从预加载 dict 获取数据
                kline_rows = kline_map.get(code, [])

                if len(kline_rows) < 60:
                    continue

                kline_df = pd.DataFrame([{
                    "trade_date": r.trade_date, "open": r.open,
                    "high": r.high, "low": r.low, "close": r.close,
                    "volume": r.volume, "amount": r.amount,
                    "turnover_rate": r.turnover_rate,
                    "change_pct": r.change_pct,
                } for r in kline_rows])

                tech_result = tech_analyzer.score(kline_df)

                # 写入 StockTechnical 表（持久化指标）
                _save_technical_indicators(tech_analyzer, kline_df, code, trade_date, session)

                # B5: Fundamentals from pre-loaded map
                fund_row = fund_map.get(code)

                fund_data = {}
                report_date = None
                if fund_row:
                    fund_data = {
                        "pe_ttm": fund_row.pe_ttm, "pb": fund_row.pb,
                        "roe": fund_row.roe, "gross_margin": fund_row.gross_margin,
                        "net_margin": fund_row.net_margin,
                        "revenue_yoy": fund_row.revenue_yoy,
                        "profit_yoy": fund_row.profit_yoy,
                        "debt_ratio": fund_row.debt_ratio,
                        "current_ratio": fund_row.current_ratio,
                        "operating_cashflow": fund_row.operating_cashflow,
                    }
                    report_date = fund_row.report_date

                # B1: 动态行业 PE
                industry = industry_map.get(code, _get_industry(code, snapshot_df))
                avg_pe = industry_pe_map.get(industry)
                if avg_pe is None:
                    # 尝试模糊匹配回退表
                    avg_pe = next(
                        (v for k, v in _FALLBACK_PE.items() if k in industry),
                        30.0
                    ) if industry else 30.0

                # B8: 传入 report_date 用于新鲜度惩罚
                fund_result = fund_analyzer.score(fund_data,
                                                  industry_avg_pe=avg_pe,
                                                  report_date=report_date)

                # B5: Money flow from pre-loaded map
                mf_rows = mf_map.get(code, [])
                # 取最近 10 条
                mf_recent = mf_rows[-10:] if len(mf_rows) > 10 else mf_rows
                mf_dicts = [{
                    "main_net_inflow": r.main_net_inflow,
                    "main_net_ratio": r.main_net_ratio,
                    "super_large_net": r.super_large_net,
                } for r in mf_recent]

                # B2: 传入市值用于资金面归一化
                market_cap = fund_row.market_cap if fund_row and fund_row.market_cap else 0
                money_result = money_analyzer.score(mf_dicts, market_cap=market_cap)

                # Sentiment
                sent_result = sent_analyzer.score(
                    code, industry,
                    sentiment_data.get("sector_flow", pd.DataFrame()),
                    sentiment_data.get("zt_pool", pd.DataFrame()),
                    sentiment_data.get("boards", pd.DataFrame()),
                )

                # Composite
                composite = scorer.compute(tech_result, fund_result,
                                           money_result, sent_result)
                composite["stock_code"] = code
                composite["stock_name"] = name
                composite["industry"] = industry
                composite["close_price"] = float(kline_df.iloc[-1]["close"])
                composite["change_pct"] = float(kline_df.iloc[-1].get("change_pct", 0) or 0)
                results.append(composite)
                scored_count += 1

            except Exception as e:
                logger.error(f"[{code}] 评分失败: {e}")

        _pipeline_status["progress"] = f"评分完成 {scored_count} 只"

        # --- Phase 4: 排名 + 写入 ---
        _pipeline_status["phase"] = "writing"
        logger.info(f"[4/4] 排名并写入... ({len(results)} 只)")
        results.sort(key=lambda x: x["total_score"], reverse=True)
        top_n = min(settings.stock_pool_size, len(results))

        # Clear today's old recommendations
        session.query(DailyRecommendation).filter_by(trade_date=trade_date).delete()

        for i, r in enumerate(results[:top_n], 1):
            rec = DailyRecommendation(
                trade_date=trade_date,
                stock_code=r["stock_code"],
                stock_name=r["stock_name"],
                rank=i,
                total_score=r["total_score"],
                technical_score=r["technical_score"],
                fundamental_score=r["fundamental_score"],
                money_flow_score=r["money_flow_score"],
                sentiment_score=r["sentiment_score"],
                close_price=r["close_price"],
                change_pct=r["change_pct"],
                risk_level=r["risk_level"],
                industry=r.get("industry", ""),
                analysis_text=_build_analysis_text(r),
                signals_json=r["signals_json"],
            )
            session.add(rec)

        session.commit()
        logger.info(f"写入 {top_n} 条推荐完成")

        # 数据质量报告
        _log_data_quality_report(stock_list, session, trade_date)

        # --- Phase 5: 回测历史推荐 ---
        _pipeline_status["phase"] = "backfill"
        try:
            backfill_results(session)
        except Exception as e:
            logger.warning(f"回测回填失败 (非致命): {e}")

        # 清除缓存
        try:
            from app.cache import cache
            cache.invalidate()
            logger.info("缓存已清除")
        except Exception:
            pass

        logger.info(f"===== 流水线完成! 写入 {top_n} 条推荐 =====")

    except Exception as e:
        logger.error(f"流水线异常: {e}")
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 数据质量报告
# ---------------------------------------------------------------------------

def _log_data_quality_report(stock_list, session, trade_date):
    """采集完成后输出数据质量报告"""
    from sqlalchemy import func, distinct

    total = len(stock_list)
    if total == 0:
        return
    codes = [c for c, _ in stock_list]

    kline_ok = session.query(func.count(distinct(StockDaily.stock_code))).filter(
        StockDaily.stock_code.in_(codes),
        StockDaily.trade_date >= trade_date - timedelta(days=3),
    ).scalar() or 0

    fund_ok = session.query(func.count(distinct(StockFundamental.stock_code))).filter(
        StockFundamental.stock_code.in_(codes),
        StockFundamental.pe_ttm != None,
    ).scalar() or 0

    mf_ok = session.query(func.count(distinct(StockMoneyFlow.stock_code))).filter(
        StockMoneyFlow.stock_code.in_(codes),
        StockMoneyFlow.trade_date >= trade_date - timedelta(days=3),
    ).scalar() or 0

    pct = lambda ok: ok * 100 // total if total else 0
    logger.info("=== 数据质量报告 ===")
    logger.info(f"股票池: {total}只")
    logger.info(f"K线覆盖: {kline_ok}/{total} ({pct(kline_ok)}%)")
    logger.info(f"基本面(PE有值): {fund_ok}/{total} ({pct(fund_ok)}%)")
    logger.info(f"资金流覆盖: {mf_ok}/{total} ({pct(mf_ok)}%)")
    logger.info("===================")


# ---------------------------------------------------------------------------
# 持久化技术指标
# ---------------------------------------------------------------------------

def _save_technical_indicators(analyzer: TechnicalAnalyzer, kline_df: pd.DataFrame,
                                code: str, trade_date, session: Session):
    """将最新技术指标写入 StockTechnical 表"""
    try:
        existing = session.query(StockTechnical).filter_by(
            stock_code=code, trade_date=trade_date
        ).first()
        if existing:
            return  # 已存在，跳过

        indicators = analyzer.get_latest_indicators(kline_df)
        tech_record = StockTechnical(
            stock_code=code,
            trade_date=trade_date,
            **indicators,
        )
        session.add(tech_record)
        session.flush()
    except Exception as e:
        logger.debug(f"[{code}] 技术指标写入失败: {e}")


# ---------------------------------------------------------------------------
# 回测: 回填历史推荐的真实收益
# ---------------------------------------------------------------------------

def backfill_results(session: Session):
    """回填过去 1-7 天推荐记录的真实收益率

    逻辑:
    1. 查找过去 7 天内还没有回测数据的推荐记录
    2. 从 StockDaily 获取推荐日后 T+1/T+3/T+5 的收盘价
    3. 计算收益率并写入 RecommendationResult
    """
    today = datetime.now().date()
    lookback_start = today - timedelta(days=10)

    # 找到有推荐但还没有回测记录的日期
    from sqlalchemy import func, and_
    rec_dates = session.query(DailyRecommendation.trade_date).filter(
        DailyRecommendation.trade_date.between(lookback_start, today - timedelta(days=1))
    ).distinct().all()

    if not rec_dates:
        logger.info("无需回测的推荐记录")
        return

    filled_count = 0
    for (rec_date,) in rec_dates:
        recs = session.query(DailyRecommendation).filter_by(trade_date=rec_date).all()

        for rec in recs:
            # 检查是否已有回测记录且已完成
            existing = session.query(RecommendationResult).filter_by(
                trade_date=rec_date, stock_code=rec.stock_code
            ).first()

            if existing and existing.close_t5 is not None:
                continue  # T+5 已有数据，完全跳过

            # 获取该股票推荐日之后的 K-line 数据
            future_bars = session.query(StockDaily).filter(
                and_(
                    StockDaily.stock_code == rec.stock_code,
                    StockDaily.trade_date > rec_date,
                )
            ).order_by(StockDaily.trade_date).limit(5).all()

            if not future_bars:
                continue

            close_t1 = future_bars[0].close if len(future_bars) >= 1 else None
            close_t3 = future_bars[2].close if len(future_bars) >= 3 else None
            close_t5 = future_bars[4].close if len(future_bars) >= 5 else None

            base_price = rec.close_price or 0
            if base_price <= 0:
                continue

            return_t1 = round((close_t1 - base_price) / base_price * 100, 2) if close_t1 else None
            return_t3 = round((close_t3 - base_price) / base_price * 100, 2) if close_t3 else None
            return_t5 = round((close_t5 - base_price) / base_price * 100, 2) if close_t5 else None

            if existing:
                # 更新已有记录
                existing.close_t1 = close_t1 or existing.close_t1
                existing.close_t3 = close_t3 or existing.close_t3
                existing.close_t5 = close_t5 or existing.close_t5
                existing.return_t1 = return_t1 if return_t1 is not None else existing.return_t1
                existing.return_t3 = return_t3 if return_t3 is not None else existing.return_t3
                existing.return_t5 = return_t5 if return_t5 is not None else existing.return_t5
                existing.verified_at = datetime.now()
            else:
                # 创建新记录
                result = RecommendationResult(
                    trade_date=rec_date,
                    stock_code=rec.stock_code,
                    stock_name=rec.stock_name,
                    recommend_score=rec.total_score,
                    close_at_recommend=rec.close_price,
                    close_t1=close_t1,
                    close_t3=close_t3,
                    close_t5=close_t5,
                    return_t1=return_t1,
                    return_t3=return_t3,
                    return_t5=return_t5,
                    verified_at=datetime.now(),
                )
                session.add(result)
                filled_count += 1

    session.commit()
    logger.info(f"回测回填完成: 新增 {filled_count} 条记录")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _build_pool_from_db(session: Session) -> list[tuple]:
    """从数据库历史数据构建股票池 (Tier 3 降级)"""
    from sqlalchemy import func

    latest_date = session.query(func.max(StockDaily.trade_date)).scalar()
    if not latest_date:
        return []

    rows = session.query(StockDaily).filter_by(trade_date=latest_date).all()

    result = []
    for r in rows:
        if r.close and r.close > 0 and "ST" not in (r.stock_name or ""):
            result.append((r.stock_code, r.stock_name or ""))

    max_size = settings.stock_pool_size * settings.pool_multiplier
    logger.info(f"数据库降级: 最近交易日 {latest_date}, 共 {len(rows)} 条, 过滤后 {len(result[:max_size])} 只")
    return result[:max_size]


def _filter_stock_pool(df) -> list[dict]:
    """过滤股票池 (PRD 4.6)，使用配置值，适配缺少列的情况"""
    if df is None or df.empty:
        return []
    filtered = df.copy()

    if "名称" in filtered.columns:
        filtered = filtered[~filtered["名称"].str.contains("ST", na=False)]
    if "最新价" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["最新价"], errors="coerce") > 0]
    if "总市值" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["总市值"], errors="coerce") > settings.filter_min_market_cap * 1e8
        ]
    if "换手率" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["换手率"], errors="coerce") < settings.filter_max_turnover
        ]
    if "涨跌幅" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["涨跌幅"], errors="coerce").abs() < settings.filter_max_change_pct
        ]

    result = []
    for _, r in filtered.iterrows():
        item = {"code": str(r["代码"]), "name": str(r["名称"])}
        try:
            item["amount"] = float(r.get("成交额", 0) or 0)
        except (ValueError, TypeError):
            item["amount"] = 0
        try:
            item["change_pct"] = float(r.get("涨跌幅", 0) or 0)
        except (ValueError, TypeError):
            item["change_pct"] = 0
        result.append(item)
    return result


def _get_industry(code: str, snapshot_df) -> str:
    """Get industry from snapshot (simplified)"""
    if snapshot_df is None or snapshot_df.empty:
        return ""
    return ""


def _build_analysis_text(r: dict) -> str:
    """Build analysis text from composite result"""
    total = r["total_score"]
    bullish = r.get("signals_bullish", [])
    bearish = r.get("signals_bearish", [])

    lines = [f"【综合评分 {total}/100】"]

    if total >= 70:
        lines.append("多因子共振偏多，适合关注。")
    elif total >= 55:
        lines.append("信号中性偏多，可轻仓试探。")
    else:
        lines.append("暂无明确方向，建议观望。")

    if bullish:
        lines.append("利多: " + "、".join(bullish[:3]))
    if bearish:
        lines.append("风险: " + "、".join(bearish[:2]))

    return "\n".join(lines)
