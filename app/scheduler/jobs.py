"""盘后定时任务: 采集 -> 计算 -> 评分 -> 写入 -> 回测"""

import logging
import threading
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
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
}


def get_pipeline_status() -> dict:
    """返回 pipeline 当前状态（线程安全）"""
    return dict(_pipeline_status)


def run_daily_pipeline():
    """每日盘后完整流水线（带并发锁）"""
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
    except Exception as e:
        _pipeline_status["last_error"] = str(e)
        _pipeline_status["phase"] = "failed"
        logger.error(f"流水线异常: {e}")
    finally:
        _pipeline_status["running"] = False
        _pipeline_status["finished_at"] = datetime.now().isoformat()
        _pipeline_lock.release()


# ---------------------------------------------------------------------------
# Pipeline 核心逻辑
# ---------------------------------------------------------------------------

def _run_pipeline_inner():
    """实际的 Pipeline 逻辑"""
    logger.info("===== 每日流水线启动 =====")
    session = get_session()

    try:
        # --- Phase 1: 快照 + 过滤 ---
        _pipeline_status["phase"] = "snapshot"
        logger.info("[1/4] 获取全A快照并过滤...")
        mc = MarketCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)

        try:
            snapshot_df = mc.collect_snapshot()
        except Exception as e:
            logger.error(f"快照获取失败: {e}")
            snapshot_df = pd.DataFrame()

        pool = _filter_stock_pool(snapshot_df)
        stock_list = [(r["code"], r["name"]) for r in pool]
        logger.info(f"过滤后股票池: {len(stock_list)} 只")
        _pipeline_status["progress"] = f"股票池 {len(stock_list)} 只"

        if not stock_list:
            logger.warning("过滤后股票池为空，跳过")
            return

        # --- Phase 2: 数据采集（各采集器独立容错） ---
        _pipeline_status["phase"] = "collecting"
        logger.info("[2/4] 数据采集...")

        try:
            mc.collect(stock_list, session)
        except Exception as e:
            logger.error(f"K线采集异常(继续执行): {e}")

        fc = FundamentalCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
        try:
            fc.collect(stock_list, session)
        except Exception as e:
            logger.error(f"基本面采集异常(继续执行): {e}")

        mfc = MoneyFlowCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
        try:
            mfc.collect(stock_list, session)
        except Exception as e:
            logger.error(f"资金流采集异常(继续执行): {e}")

        sc = SentimentCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
        sentiment_data = {"sector_flow": pd.DataFrame(), "boards": pd.DataFrame(),
                          "zt_pool": pd.DataFrame(), "north_flow": pd.DataFrame()}
        try:
            sentiment_data = sc.collect()
        except Exception as e:
            logger.error(f"情绪数据采集异常(使用空数据继续): {e}")

        # Enrich fundamentals with spot data
        if snapshot_df is not None and not snapshot_df.empty:
            for code, name in stock_list[:50]:
                try:
                    spot_row = snapshot_df[snapshot_df["代码"] == code]
                    if not spot_row.empty:
                        fc.enrich_from_spot(code, spot_row.iloc[0].to_dict(), session)
                except Exception:
                    pass

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
        results = []
        scored_count = 0

        for code, name in stock_list:
            try:
                kline_rows = session.query(StockDaily).filter_by(
                    stock_code=code
                ).order_by(StockDaily.trade_date).all()

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

                # Fundamentals
                fund_row = session.query(StockFundamental).filter_by(
                    stock_code=code
                ).order_by(StockFundamental.report_date.desc()).first()

                fund_data = {}
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
                fund_result = fund_analyzer.score(fund_data)

                # Money flow
                mf_rows = session.query(StockMoneyFlow).filter_by(
                    stock_code=code
                ).order_by(StockMoneyFlow.trade_date.desc()).limit(10).all()
                mf_dicts = [{
                    "main_net_inflow": r.main_net_inflow,
                    "main_net_ratio": r.main_net_ratio,
                    "super_large_net": r.super_large_net,
                } for r in reversed(mf_rows)]
                money_result = money_analyzer.score(mf_dicts)

                # Sentiment
                industry = industry_map.get(code, _get_industry(code, snapshot_df))
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

def _filter_stock_pool(df) -> list[dict]:
    """过滤股票池 (PRD 4.6)"""
    if df is None or df.empty:
        return []
    filtered = df.copy()
    filtered = filtered[~filtered["名称"].str.contains("ST", na=False)]
    filtered = filtered[filtered["最新价"] > 0]
    filtered = filtered[filtered["总市值"] > 20e8]
    filtered = filtered[filtered["换手率"] < 20]
    filtered = filtered[filtered["涨跌幅"].abs() < 9.5]

    return [{"code": str(r["代码"]), "name": str(r["名称"])}
            for _, r in filtered.iterrows()]


def _get_industry(code: str, snapshot_df) -> str:
    """Get industry from snapshot (simplified)"""
    if snapshot_df is None or snapshot_df.empty:
        return ""
    return ""


def _build_analysis_text(r: dict) -> str:
    """Build analysis text from composite result"""
    bullish = r.get("signals_bullish", [])
    bearish = r.get("signals_bearish", [])
    lines = [f"【综合评分 {r['total_score']}/100 - {r.get('advice', '')}】"]
    if bullish:
        lines.append("看多信号: " + ", ".join(bullish[:5]))
    if bearish:
        lines.append("风险提示: " + ", ".join(bearish[:3]))
    return "\n".join(lines)
