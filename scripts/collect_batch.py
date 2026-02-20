"""批量数据采集脚本 - 采集Top500市值股票的K线、资金流、基本面数据"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from app.db import get_session
from app.collectors.market import MarketCollector
from app.collectors.money_flow import MoneyFlowCollector
from app.collectors.fundamental import FundamentalCollector
from app.models.database import StockDaily, StockMoneyFlow, StockFundamental
from sqlalchemy import func


def get_top_stocks(n=500):
    """获取Top N市值股票"""
    import akshare as ak
    logger.info("获取全A股快照...")
    df = ak.stock_zh_a_spot_em()

    # Filter
    df = df[~df["名称"].str.contains("ST", na=False)]
    df = df[df["最新价"] > 0]
    df = df[df["总市值"] > 20e8]
    df = df[df["换手率"] < 20]
    df = df[df["涨跌幅"].abs() < 9.5]

    # Sort by market cap descending, take top N
    df = df.sort_values("总市值", ascending=False).head(n)
    stock_list = [(str(r["代码"]), str(r["名称"])) for _, r in df.iterrows()]
    logger.info(f"目标股票池: {len(stock_list)} 只 (Top {n} by market cap)")
    return stock_list


def collect_klines(stock_list, session):
    """采集K线数据 (跳过已有的)"""
    mc = MarketCollector(delay=0.3, retry=2)

    # Check which stocks already have sufficient K-line data
    existing = set()
    for code, _ in stock_list:
        count = session.query(StockDaily).filter_by(stock_code=code).count()
        if count >= 200:
            existing.add(code)

    need_collect = [(c, n) for c, n in stock_list if c not in existing]
    logger.info(f"K线: {len(existing)} 只已有数据, {len(need_collect)} 只需采集")

    total = 0
    for i, (code, name) in enumerate(need_collect):
        try:
            n = mc.collect_kline(code, name, session)
            total += n
            if (i + 1) % 50 == 0:
                logger.info(f"  K线进度: {i+1}/{len(need_collect)}, 新增 {total} 条")
        except Exception as e:
            logger.error(f"[{code}] K线失败: {e}")

    logger.info(f"K线采集完成: 新增 {total} 条, 共 {len(existing) + len(need_collect)} 只")
    return total


def collect_money_flow(stock_list, session):
    """采集资金流向数据"""
    mfc = MoneyFlowCollector(delay=0.3, retry=2)

    # Check existing
    existing = set()
    for code, _ in stock_list:
        count = session.query(StockMoneyFlow).filter_by(stock_code=code).count()
        if count >= 5:
            existing.add(code)

    need_collect = [(c, n) for c, n in stock_list if c not in existing]
    logger.info(f"资金流: {len(existing)} 只已有数据, {len(need_collect)} 只需采集")

    total = 0
    for i, (code, name) in enumerate(need_collect):
        try:
            n = mfc.collect_one(code, session)
            total += n
            if (i + 1) % 50 == 0:
                logger.info(f"  资金流进度: {i+1}/{len(need_collect)}, 新增 {total} 条")
        except Exception as e:
            logger.error(f"[{code}] 资金流失败: {e}")

    logger.info(f"资金流采集完成: 新增 {total} 条")
    return total


def collect_fundamentals(stock_list, session):
    """采集基本面数据 (API + spot数据补充)"""
    fc = FundamentalCollector(delay=0.3, retry=2)

    # Check existing
    existing = set()
    for code, _ in stock_list:
        count = session.query(StockFundamental).filter_by(stock_code=code).count()
        if count >= 1:
            existing.add(code)

    need_collect = [(c, n) for c, n in stock_list if c not in existing]
    logger.info(f"基本面: {len(existing)} 只已有数据, {len(need_collect)} 只需采集")

    total = 0
    for i, (code, name) in enumerate(need_collect):
        try:
            n = fc.collect_one(code, session)
            total += n
            if (i + 1) % 50 == 0:
                logger.info(f"  基本面进度: {i+1}/{len(need_collect)}, 新增 {total} 条")
        except Exception as e:
            logger.error(f"[{code}] 基本面失败: {e}")

    logger.info(f"基本面采集完成: 新增 {total} 条")

    # Enrich with spot data (PE/PB/市值) for ALL stocks
    enrich_fundamentals_from_spot(stock_list, session, fc)

    return total


def enrich_fundamentals_from_spot(stock_list, session, fc=None):
    """用实时行情补充基本面PE/PB/市值数据"""
    import akshare as ak
    if fc is None:
        fc = FundamentalCollector(delay=0.3, retry=2)

    logger.info("正在用实时行情补充基本面数据(PE/PB/市值)...")
    try:
        spot_df = ak.stock_zh_a_spot_em()
    except Exception as e:
        logger.error(f"获取实时行情失败: {e}")
        return 0

    enriched = 0
    codes_in_list = {c for c, _ in stock_list}
    for _, spot_row in spot_df.iterrows():
        code = str(spot_row.get("代码", ""))
        if code not in codes_in_list:
            continue
        # Check if stock has fundamental data; if not, create a stub record
        fund = session.query(StockFundamental).filter_by(stock_code=code).first()
        if not fund:
            from datetime import date as _date
            fund = StockFundamental(stock_code=code, report_date=_date.today())
            session.add(fund)
            session.flush()

        try:
            fc.enrich_from_spot(code, spot_row.to_dict(), session)
            enriched += 1
        except Exception:
            pass

    session.commit()
    logger.info(f"实时数据补充完成: {enriched} 只股票已更新PE/PB/市值")


def rescore_all(stock_list, session):
    """重新评分所有有数据的股票"""
    import pandas as pd
    from datetime import datetime
    from app.analyzers.technical import TechnicalAnalyzer
    from app.analyzers.fundamental import FundamentalAnalyzer
    from app.analyzers.money_flow import MoneyFlowAnalyzer
    from app.analyzers.sentiment import SentimentAnalyzer
    from app.analyzers.scorer import CompositeScorer
    from app.collectors.sentiment import SentimentCollector
    from app.models.database import DailyRecommendation

    tech_analyzer = TechnicalAnalyzer()
    fund_analyzer = FundamentalAnalyzer()
    money_analyzer = MoneyFlowAnalyzer()
    sent_analyzer = SentimentAnalyzer()
    scorer = CompositeScorer()

    # Industry mapping
    from app.collectors.industry import get_industry_map
    industry_map = get_industry_map()
    logger.info(f"行业映射: {len(industry_map)} 只")

    # Collect sentiment data
    sc = SentimentCollector(delay=0.3, retry=2)
    sentiment_data = sc.collect()

    trade_date = datetime.now().date()
    results = []
    scored = 0

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
            industry = industry_map.get(code, "")
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
            scored += 1

        except Exception as e:
            logger.error(f"[{code}] 评分失败: {e}")

    logger.info(f"评分完成: {scored} 只股票")

    # Write recommendations
    results.sort(key=lambda x: x["total_score"], reverse=True)
    top_n = min(100, len(results))

    session.query(DailyRecommendation).filter_by(trade_date=trade_date).delete()

    for i, r in enumerate(results[:top_n], 1):
        bullish = r.get("signals_bullish", [])
        bearish = r.get("signals_bearish", [])
        lines = [f"综合评分 {r['total_score']}/100 - {r.get('advice', '')}"]
        if bullish:
            lines.append("看多: " + ", ".join(bullish[:5]))
        if bearish:
            lines.append("风险: " + ", ".join(bearish[:3]))

        import json
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
            analysis_text="\n".join(lines),
            signals_json=r["signals_json"],
        )
        session.add(rec)

    session.commit()
    logger.info(f"写入 {top_n} 条推荐 (Top1: {results[0]['stock_name']} {results[0]['total_score']:.1f}分)")
    return top_n


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=500, help="Top N stocks by market cap")
    parser.add_argument("--skip-kline", action="store_true", help="Skip K-line collection")
    parser.add_argument("--skip-money", action="store_true", help="Skip money flow collection")
    parser.add_argument("--skip-fund", action="store_true", help="Skip fundamental collection")
    parser.add_argument("--score-only", action="store_true", help="Only run scoring")
    args = parser.parse_args()

    session = get_session()
    t0 = time.time()

    stock_list = get_top_stocks(args.top)

    if args.score_only:
        rescore_all(stock_list, session)
    else:
        if not args.skip_kline:
            collect_klines(stock_list, session)
        if not args.skip_money:
            collect_money_flow(stock_list, session)
        if not args.skip_fund:
            collect_fundamentals(stock_list, session)
        rescore_all(stock_list, session)

    elapsed = time.time() - t0
    logger.info(f"总耗时: {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")
    session.close()
