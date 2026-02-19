"""盘后定时任务: 采集 -> 计算 -> 评分 -> 写入"""

import logging
from datetime import datetime

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
    StockDaily, StockFundamental, StockMoneyFlow, DailyRecommendation,
)

logger = logging.getLogger(__name__)


def run_daily_pipeline():
    """每日盘后完整流水线"""
    logger.info("===== 每日流水线启动 =====")
    session = get_session()

    try:
        # --- Phase 1: 快照 + 过滤 ---
        logger.info("[1/4] 获取全A快照并过滤...")
        mc = MarketCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)

        try:
            snapshot_df = mc.collect_snapshot()
        except Exception as e:
            logger.error(f"快照获取失败: {e}")
            return

        pool = _filter_stock_pool(snapshot_df)
        stock_list = [(r["code"], r["name"]) for r in pool]
        logger.info(f"过滤后股票池: {len(stock_list)} 只")

        if not stock_list:
            logger.warning("过滤后股票池为空，跳过")
            return

        # --- Phase 2: 数据采集 ---
        logger.info("[2/4] 数据采集...")
        mc.collect(stock_list, session)

        fc = FundamentalCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
        fc.collect(stock_list, session)

        mfc = MoneyFlowCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
        mfc.collect(stock_list, session)

        sc = SentimentCollector(delay=settings.akshare_delay, retry=settings.akshare_retry)
        sentiment_data = sc.collect()

        # Enrich fundamentals with spot data
        if snapshot_df is not None and not snapshot_df.empty:
            for code, name in stock_list[:50]:  # Top 50 only to save time
                try:
                    spot_row = snapshot_df[snapshot_df["代码"] == code]
                    if not spot_row.empty:
                        fc.enrich_from_spot(code, spot_row.iloc[0].to_dict(), session)
                except Exception:
                    pass

        # --- Phase 3: 评分 ---
        logger.info("[3/4] 评分计算...")
        tech_analyzer = TechnicalAnalyzer()
        fund_analyzer = FundamentalAnalyzer()
        money_analyzer = MoneyFlowAnalyzer()
        sent_analyzer = SentimentAnalyzer()
        scorer = CompositeScorer()

        trade_date = datetime.now().date()
        results = []

        for code, name in stock_list:
            try:
                # K-line data
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
                industry = _get_industry(code, snapshot_df)
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

            except Exception as e:
                logger.error(f"[{code}] 评分失败: {e}")

        # --- Phase 4: 排名 + 写入 ---
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
        logger.info(f"===== 流水线完成! 写入 {top_n} 条推荐 =====")

    except Exception as e:
        logger.error(f"流水线异常: {e}")
        session.rollback()
    finally:
        session.close()


def _filter_stock_pool(df) -> list[dict]:
    """过滤股票池 (PRD 4.6)"""
    if df is None or df.empty:
        return []
    filtered = df.copy()
    # Exclude ST
    filtered = filtered[~filtered["名称"].str.contains("ST", na=False)]
    # Exclude suspended (price=0 or NaN)
    filtered = filtered[filtered["最新价"] > 0]
    # Market cap > 20B yuan
    filtered = filtered[filtered["总市值"] > 20e8]
    # Turnover < 20%
    filtered = filtered[filtered["换手率"] < 20]
    # Change < 9.5% (exclude limit-up/down)
    filtered = filtered[filtered["涨跌幅"].abs() < 9.5]

    return [{"code": str(r["代码"]), "name": str(r["名称"])}
            for _, r in filtered.iterrows()]


def _get_industry(code: str, snapshot_df) -> str:
    """Get industry from snapshot (simplified)"""
    if snapshot_df is None or snapshot_df.empty:
        return ""
    # snapshot doesn't have industry column directly, return empty
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
