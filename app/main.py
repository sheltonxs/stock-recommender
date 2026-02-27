"""A股智选 - 每日股票推荐系统 (v3.1 - 性能优化版)"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.cache import cache, get_cache_ttl
from app.config import settings
from app.db import get_db_dep, get_session
from app.models.database import (
    StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation, RecommendationResult,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (替代已废弃的 on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _scheduler = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.scheduler.jobs import run_daily_pipeline
        _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        _scheduler.add_job(
            run_daily_pipeline, "cron",
            hour=settings.schedule_collect_hour,
            minute=settings.schedule_collect_minute,
            day_of_week="mon-fri",
            id="daily_pipeline",
        )
        _scheduler.start()
        logger.info("APScheduler 启动成功, 每日 %02d:%02d 执行",
                     settings.schedule_collect_hour, settings.schedule_collect_minute)
    except Exception as e:
        logger.warning(f"调度器启动失败 (可忽略): {e}")

    # Preload cache in background so first homepage visit is fast
    import threading
    def _warm_cache():
        try:
            _build_market_indices()
            _build_sectors()
            logger.info("首页缓存预热完成")
        except Exception as e:
            logger.warning(f"缓存预热失败(可忽略): {e}")
    threading.Thread(target=_warm_cache, daemon=True).start()

    yield

    # Shutdown
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler 已关闭")


app = FastAPI(title="A股智选", lifespan=lifespan)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Helper: build template data from DB
# ---------------------------------------------------------------------------

def _get_latest_trade_date(session: Session) -> date | None:
    row = session.query(DailyRecommendation.trade_date)\
        .order_by(DailyRecommendation.trade_date.desc()).first()
    return row[0] if row else None


def _build_recommendations(session: Session, trade_date) -> list[dict]:
    if trade_date is None:
        return []
    recs = session.query(DailyRecommendation)\
        .filter_by(trade_date=trade_date)\
        .order_by(DailyRecommendation.rank).all()

    result = []
    for r in recs:
        sigs = json.loads(r.signals_json) if r.signals_json else {"bullish": [], "bearish": []}
        result.append({
            "rank": r.rank,
            "code": r.stock_code,
            "name": r.stock_name,
            "industry": r.industry or "",
            "total_score": r.total_score,
            "technical_score": r.technical_score or 0,
            "fundamental_score": r.fundamental_score or 0,
            "money_flow_score": r.money_flow_score or 0,
            "sentiment_score": r.sentiment_score or 0,
            "close_price": r.close_price or 0,
            "change_pct": r.change_pct or 0,
            "risk_level": r.risk_level or "中",
            "advice": _score_to_advice(r.total_score),
            "bullish": sigs.get("bullish", []),
            "bearish": sigs.get("bearish", []),
            "warning": sigs.get("bearish", ["注意仓位控制"])[:1],
        })
    return result


def _score_to_advice(score: float) -> str:
    if score >= 80:
        return "强烈看多"
    if score >= 70:
        return "偏多"
    if score >= 55:
        return "中性偏多"
    if score >= 40:
        return "中性"
    return "偏空"


def _build_market_indices_uncached() -> list[dict]:
    """从 AKShare 获取市场指数（不缓存）"""
    defaults = [
        {"name": "上证指数", "code": "000001", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
        {"name": "深证成指", "code": "399001", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
        {"name": "创业板指", "code": "399006", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
        {"name": "科创50", "code": "000688", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
    ]
    try:
        import akshare as ak
        df = ak.stock_zh_index_spot_sina()
        code_map = {
            "上证指数": "sh000001",
            "深证成指": "sz399001",
            "创业板指": "sz399006",
            "科创50": "sh000688",
        }
        for item in defaults:
            sina_code = code_map.get(item["name"])
            if not sina_code:
                continue
            row = df[df["代码"] == sina_code]
            if not row.empty:
                r = row.iloc[0]
                item["price"] = round(float(r.get("最新价", 0)), 2)
                item["change"] = round(float(r.get("涨跌额", 0)), 2)
                item["change_pct"] = round(float(r.get("涨跌幅", 0)), 2)
                vol = float(r.get("成交额", 0))
                item["volume"] = f"{vol/1e8:.0f}亿" if vol else "—"
    except Exception as e:
        logger.warning(f"Failed to fetch market indices: {e}")
    return defaults


def _build_market_indices() -> list[dict]:
    """获取市场指数（带缓存 + 超时保护）"""
    ttl = get_cache_ttl(trading_ttl=300, non_trading_ttl=1800)
    result = cache.get_or_set("market_indices", _build_market_indices_uncached, ttl, timeout=8.0)
    if result is None:
        return [
            {"name": "上证指数", "code": "000001", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
            {"name": "深证成指", "code": "399001", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
            {"name": "创业板指", "code": "399006", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
            {"name": "科创50", "code": "000688", "price": 0, "change": 0, "change_pct": 0, "volume": "—"},
        ]
    return result


def _build_sectors_uncached() -> list[dict]:
    """从 AKShare 获取板块数据，失败时使用文件缓存"""
    BOARD_CACHE = Path(__file__).resolve().parent.parent / "data" / "board_cache.json"
    EMPTY = [{"name": "暂无数据", "value": 0, "change_pct": 0, "amount": 0, "leader": ""}]

    # Tier 1: 实时 API
    df = None
    from_api = False
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            from_api = True
    except Exception as e:
        logger.warning(f"板块API失败: {e}")

    # Tier 2: 文件缓存
    if df is None or df.empty:
        try:
            if BOARD_CACHE.exists():
                cache = json.loads(BOARD_CACHE.read_text())
                df = pd.DataFrame(cache["data"])
                logger.info(f"板块热力图使用缓存 ({cache.get('date', 'unknown')})")
        except Exception as e:
            logger.warning(f"板块缓存加载失败: {e}")

    if df is None or df.empty:
        return EMPTY

    # API 成功时保存完整数据到缓存（在过滤前）
    if from_api:
        try:
            BOARD_CACHE.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "data": df.to_dict(orient="records"),
            }
            BOARD_CACHE.write_text(json.dumps(cache_data, ensure_ascii=False, default=str))
        except Exception:
            pass

    try:
        df = df[~df["板块名称"].str.contains("Ⅱ|Ⅲ", na=False)]
        df = df.sort_values("总市值", ascending=False).head(20)
        sectors = []
        for _, row in df.iterrows():
            mkt_cap = float(row.get("总市值", 0) or 0) / 1e8
            change = float(row.get("涨跌幅", 0) or 0)
            sectors.append({
                "name": str(row["板块名称"]),
                "value": round(abs(change), 2),
                "change_pct": round(change, 2),
                "amount": round(mkt_cap, 0),
                "leader": str(row.get("领涨股票", "") or ""),
            })
        return sectors if sectors else EMPTY
    except Exception as e:
        logger.warning(f"板块数据解析失败: {e}")
        return EMPTY


def _build_sectors() -> list[dict]:
    """获取板块数据（带缓存 + 超时保护）"""
    ttl = get_cache_ttl(trading_ttl=300, non_trading_ttl=1800)
    result = cache.get_or_set("sectors", _build_sectors_uncached, ttl, timeout=8.0)
    if result is None:
        return [{"name": "暂无数据", "value": 0, "change_pct": 0, "amount": 0, "leader": ""}]
    return result


def _build_sankey(session: Session) -> dict:
    """Build sankey data from recommendations"""
    trade_date = _get_latest_trade_date(session)
    recs = session.query(DailyRecommendation).filter(
        DailyRecommendation.trade_date == trade_date
    ).all() if trade_date else []

    sources = set()
    targets = set()
    links = []

    industry_scores = {}
    for r in recs:
        ind = r.industry or "其他"
        if ind not in industry_scores:
            industry_scores[ind] = {"total": 0, "count": 0}
        industry_scores[ind]["total"] += r.total_score
        industry_scores[ind]["count"] += 1

    fund_types = ["主力资金", "北向资金", "融资余额"]
    for ft in fund_types:
        sources.add(ft)
        for ind, data in sorted(industry_scores.items(), key=lambda x: -x[1]["total"])[:8]:
            targets.add(ind)
            links.append({"source": ft, "target": ind, "value": round(data["total"] / data["count"] / 10, 1)})

    all_nodes = list(sources | targets)
    return {
        "nodes": [{"name": n} for n in all_nodes],
        "links": links,
    } if links else {"nodes": [{"name": "暂无数据"}], "links": []}


def _build_sentiment(session: Session) -> dict:
    """Build sentiment gauge data"""
    trade_date = _get_latest_trade_date(session)
    if not trade_date:
        return {"fear_greed_index": 50, "label": "中性", "advance": 0, "decline": 0,
                "flat": 0, "limit_up": 0, "limit_down": 0, "total_amount": "0亿", "avg_turnover": 0}

    recs = session.query(DailyRecommendation).filter_by(trade_date=trade_date).all()
    advance = sum(1 for r in recs if (r.change_pct or 0) > 0)
    decline = sum(1 for r in recs if (r.change_pct or 0) < 0)
    flat = len(recs) - advance - decline

    avg_score = sum(r.total_score for r in recs) / len(recs) if recs else 50

    return {
        "fear_greed_index": round(avg_score),
        "label": "偏贪婪" if avg_score >= 60 else "中性" if avg_score >= 40 else "偏恐惧",
        "advance": advance,
        "decline": decline,
        "flat": flat,
        "limit_up": 0,
        "limit_down": 0,
        "total_amount": "0亿",
        "avg_turnover": 0,
    }


def _build_kline_data(code: str, session: Session) -> dict:
    """Build K-line + indicator data for detail page (with cache)"""
    cache_key = f"kline_{code}"
    cached = cache.get(cache_key, ttl=600)
    if cached:
        return cached

    rows = session.query(StockDaily).filter_by(
        stock_code=code
    ).order_by(StockDaily.trade_date).all()

    if not rows:
        empty = {"kline": [], "ma5": [], "ma10": [], "ma20": [], "ma60": [],
                 "boll_upper": [], "boll_mid": [], "boll_lower": [],
                 "dif": [], "dea": [], "macd_hist": [],
                 "rsi6": [], "rsi12": [], "rsi24": [],
                 "kdj_k": [], "kdj_d": [], "kdj_j": [], "vol_colors": []}
        return empty

    kline = [{"time": str(r.trade_date), "open": r.open, "high": r.high,
              "low": r.low, "close": r.close, "volume": r.volume} for r in rows]

    from app.analyzers.technical import TechnicalAnalyzer
    df = pd.DataFrame([{
        "trade_date": r.trade_date, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
        "amount": r.amount, "turnover_rate": r.turnover_rate,
        "change_pct": r.change_pct,
    } for r in rows])

    analyzer = TechnicalAnalyzer()
    df = analyzer.compute_indicators(df.copy())

    def to_list(series):
        return [None if pd.isna(v) else round(float(v), 4) for v in series]

    vol_colors = []
    for r in rows:
        vol_colors.append("#EF4444" if (r.close or 0) >= (r.open or 0) else "#22C55E")

    result = {
        "kline": kline,
        "ma5": to_list(df["ma5"]) if "ma5" in df else [],
        "ma10": to_list(df["ma10"]) if "ma10" in df else [],
        "ma20": to_list(df["ma20"]) if "ma20" in df else [],
        "ma60": to_list(df["ma60"]) if "ma60" in df else [],
        "boll_upper": to_list(df["boll_upper"]) if "boll_upper" in df else [],
        "boll_mid": to_list(df["boll_mid"]) if "boll_mid" in df else [],
        "boll_lower": to_list(df["boll_lower"]) if "boll_lower" in df else [],
        "dif": to_list(df["macd_dif"]) if "macd_dif" in df else [],
        "dea": to_list(df["macd_dea"]) if "macd_dea" in df else [],
        "macd_hist": to_list(df["macd_hist"]) if "macd_hist" in df else [],
        "rsi6": to_list(df["rsi_6"]) if "rsi_6" in df else [],
        "rsi12": to_list(df["rsi_12"]) if "rsi_12" in df else [],
        "rsi24": to_list(df["rsi_24"]) if "rsi_24" in df else [],
        "kdj_k": to_list(df["kdj_k"]) if "kdj_k" in df else [],
        "kdj_d": to_list(df["kdj_d"]) if "kdj_d" in df else [],
        "kdj_j": to_list(df["kdj_j"]) if "kdj_j" in df else [],
        "vol_colors": vol_colors,
    }

    cache.set(cache_key, result)
    return result


def _build_fundamentals(code: str, session: Session) -> dict:
    row = session.query(StockFundamental).filter_by(
        stock_code=code
    ).order_by(StockFundamental.report_date.desc()).first()

    if not row:
        return {"pe": 0, "pb": 0, "roe": 0, "gross_margin": 0,
                "net_margin": 0, "revenue_yoy": 0, "profit_yoy": 0,
                "debt_ratio": 0, "market_cap": 0, "dividend_yield": 0,
                "industry_pe": 30.0}

    return {
        "pe": row.pe_ttm or 0,
        "pb": row.pb or 0,
        "roe": row.roe or 0,
        "gross_margin": row.gross_margin or 0,
        "net_margin": row.net_margin or 0,
        "revenue_yoy": row.revenue_yoy or 0,
        "profit_yoy": row.profit_yoy or 0,
        "debt_ratio": row.debt_ratio or 0,
        "market_cap": row.market_cap or 0,
        "dividend_yield": 0,
        "industry_pe": 30.0,
    }


def _build_money_flow(code: str, session: Session) -> list[dict]:
    rows = session.query(StockMoneyFlow).filter_by(
        stock_code=code
    ).order_by(StockMoneyFlow.trade_date.desc()).limit(5).all()

    return [{
        "date": str(r.trade_date)[5:],
        "main": int(r.main_net_inflow or 0),
        "north": 0,
        "super_large": int(r.super_large_net or 0),
        "large": int(r.large_net or 0),
        "medium": int(r.medium_net or 0),
        "small": int(r.small_net or 0),
    } for r in rows]


def _build_smart_advice(rec, tech_row, fund_row, kline_rows) -> dict:
    """基于个股数据生成具体操作建议

    同时参考绝对分数和相对排名(rank)，避免数据不完整时所有股票都显示"偏空"。
    """
    total = rec.total_score or 0
    close = rec.close_price or 0
    rank = rec.rank or 100

    # --- 止损价: 基于 MA20 或近期低点 ---
    if tech_row and tech_row.ma20 and close > 0 and tech_row.ma20 * 0.95 <= close <= tech_row.ma20 * 1.10:
        stop_price = round(tech_row.ma20 * 0.98, 2)
        stop_pct = round((stop_price - close) / close * 100, 1)
        stop_loss = f"参考止损 {stop_price} 元 (MA20下方2%, 距当前{stop_pct}%)"
    elif kline_rows:
        recent = kline_rows[-20:] if len(kline_rows) >= 20 else kline_rows
        recent_low = min(r.low for r in recent if r.low)
        stop_price = round(recent_low * 0.98, 2)
        stop_loss = f"参考止损 {stop_price} 元 (近20日低点下方)"
    else:
        stop_loss = "暂无数据"

    # --- 买入区间: 基于 MA 支撑 ---
    if tech_row and tech_row.ma10:
        buy_low = round(tech_row.ma10 * 0.99, 2)
        buy_high = round((tech_row.ma5 * 1.01) if tech_row.ma5 else (close * 1.01), 2)
        buy_zone = f"{buy_low} - {buy_high} 元"
    elif close > 0:
        buy_zone = f"{round(close * 0.98, 2)} - {round(close * 1.02, 2)} 元"
    else:
        buy_zone = "暂无数据"

    # --- 利润目标: 基于 BOLL 上轨或近期高点 ---
    if tech_row and tech_row.boll_upper and close > 0 and tech_row.boll_upper > close:
        target_price = round(tech_row.boll_upper, 2)
        target_pct = round((target_price - close) / close * 100, 1)
        target = f"短线目标 {target_price} 元 (BOLL上轨, +{target_pct}%)"
    elif kline_rows and close > 0:
        recent = kline_rows[-20:] if len(kline_rows) >= 20 else kline_rows
        recent_high = max(r.high for r in recent if r.high)
        target_pct = round((recent_high - close) / close * 100, 1)
        target = f"关注前高 {round(recent_high, 2)} 元 ({'+' if target_pct > 0 else ''}{target_pct}%)"
    else:
        target = "关注前高压力位"

    # --- 仓位 & 建议: 结合绝对分数 + 相对排名 ---
    # 绝对分数优先；但当数据不完整导致分数普遍偏低时，排名作为补充信号
    if total >= 80:
        position = "可配置 5%-8% 仓位"
    elif total >= 70 or (total >= 50 and rank <= 5):
        position = "可配置 3%-5% 仓位"
    elif total >= 55 or (total >= 40 and rank <= 20):
        position = "轻仓试探 1%-3%"
    elif rank <= 30:
        position = "轻仓试探 1%-2%"
    else:
        position = "暂不建仓，观望为主"

    lines = []
    tech_score = rec.technical_score or 0

    if total >= 70:
        lines.append(f"综合评分{total:.0f}分，多因子共振偏多。")
        if tech_row and tech_row.ma5 and tech_row.ma10 and tech_row.ma5 > tech_row.ma10:
            lines.append("短期均线多头排列，趋势向上。")
        if fund_row and fund_row.pe_ttm and 0 < fund_row.pe_ttm < 20:
            lines.append(f"PE(TTM)={fund_row.pe_ttm:.1f}，估值处于低位区间。")
        lines.append(f"建议在 {buy_zone} 区间分批建仓，{position}。")
    elif total >= 55 or (rank <= 10 and tech_score >= 60):
        lines.append(f"综合评分{total:.0f}分(排名第{rank})，信号中性偏多。")
        if tech_score >= 65:
            lines.append("技术面表现较好，关注趋势延续性。")
        lines.append(f"可在 {buy_zone} 附近轻仓试探，严格止损。")
    elif rank <= 30 and tech_score >= 50:
        lines.append(f"综合评分{total:.0f}分(排名第{rank})，技术面{tech_score:.0f}分尚可。")
        lines.append(f"可关注 {buy_zone} 区间，轻仓操作需严守止损纪律。")
    else:
        lines.append(f"综合评分{total:.0f}分，暂无明确多头信号。")
        lines.append("建议观望，等待趋势确认后再考虑介入。")

    return {
        "text": "".join(lines),
        "stop_loss": stop_loss,
        "buy_zone": buy_zone,
        "target": target,
        "position": position,
    }


def _build_analysis(code: str, session: Session) -> dict:
    rec = session.query(DailyRecommendation).filter_by(
        stock_code=code
    ).order_by(DailyRecommendation.trade_date.desc()).first()

    if not rec:
        return {
            "technical_summary": "中性",
            "sections": [],
            "advice": "暂无数据",
            "stop_loss": "暂无数据",
            "buy_zone": "暂无数据",
            "target": "暂无数据",
            "position": "暂无数据",
        }

    sigs = json.loads(rec.signals_json) if rec.signals_json else {"bullish": [], "bearish": []}
    bullish = sigs.get("bullish", [])
    bearish = sigs.get("bearish", [])

    sections = []
    trend_signals = [{"text": s, "type": "bullish"} for s in bullish if "均线" in s or "MACD" in s or "MA" in s]
    if trend_signals:
        sections.append({"title": "趋势研判", "signals": trend_signals})

    vol_signals = [{"text": s, "type": "bullish"} for s in bullish if "量" in s or "OBV" in s]
    if vol_signals:
        sections.append({"title": "量能分析", "signals": vol_signals})

    channel_signals = [{"text": s, "type": "bullish"} for s in bullish if "BOLL" in s or "通道" in s]
    if channel_signals:
        sections.append({"title": "通道位置", "signals": channel_signals})

    ob_signals = [{"text": s, "type": "bullish"} for s in bullish if "RSI" in s or "KDJ" in s]
    warning_signals = [{"text": s, "type": "warning"} for s in bearish]
    all_ob = ob_signals + warning_signals
    if all_ob:
        sections.append({"title": "超买超卖", "signals": all_ob})

    if not sections and (bullish or bearish):
        generic = [{"text": s, "type": "bullish"} for s in bullish] + \
                  [{"text": s, "type": "warning"} for s in bearish]
        sections.append({"title": "综合信号", "signals": generic})

    total = rec.total_score or 0
    if total >= 70:
        summary = "偏多"
    elif total >= 50:
        summary = "中性"
    else:
        summary = "偏空"

    # 获取技术指标和基本面数据
    tech_row = session.query(StockTechnical).filter_by(
        stock_code=code
    ).order_by(StockTechnical.trade_date.desc()).first()

    fund_row = session.query(StockFundamental).filter_by(
        stock_code=code
    ).order_by(StockFundamental.report_date.desc()).first()

    kline_rows = session.query(StockDaily).filter_by(
        stock_code=code
    ).order_by(StockDaily.trade_date).all()

    advice = _build_smart_advice(rec, tech_row, fund_row, kline_rows)

    return {
        "technical_summary": summary,
        "sections": sections,
        "advice": advice["text"],
        "stop_loss": advice["stop_loss"],
        "buy_zone": advice["buy_zone"],
        "target": advice["target"],
        "position": advice["position"],
    }


def _build_history_data(session: Session) -> list[dict]:
    """构建历史数据 - 优先使用真实回测，否则用基础统计"""
    # 先查真实回测数据
    result_dates = session.query(
        RecommendationResult.trade_date,
        func.count(RecommendationResult.id).label("count"),
        func.avg(RecommendationResult.recommend_score).label("avg_score"),
        func.avg(RecommendationResult.return_t1).label("avg_return_t1"),
        func.avg(RecommendationResult.return_t3).label("avg_return_t3"),
        func.avg(RecommendationResult.return_t5).label("avg_return_t5"),
    ).filter(
        RecommendationResult.return_t1.isnot(None)
    ).group_by(RecommendationResult.trade_date)\
     .order_by(RecommendationResult.trade_date.desc())\
     .limit(30).all()

    if result_dates:
        history_data = []
        for d in reversed(result_dates):
            # 计算真实胜率 (T+1 收益 > 0 的比例)
            total_count = session.query(func.count(RecommendationResult.id)).filter(
                RecommendationResult.trade_date == d.trade_date,
                RecommendationResult.return_t1.isnot(None),
            ).scalar() or 1
            win_count = session.query(func.count(RecommendationResult.id)).filter(
                RecommendationResult.trade_date == d.trade_date,
                RecommendationResult.return_t1 > 0,
            ).scalar() or 0
            win_rate = round(win_count / total_count * 100, 1) if total_count > 0 else 0

            history_data.append({
                "date": str(d.trade_date),
                "total_recommended": d.count,
                "count": d.count,
                "avg_score": round(float(d.avg_score), 1) if d.avg_score else 0,
                "win_rate": win_rate,
                "avg_return": round(float(d.avg_return_t1), 2) if d.avg_return_t1 is not None else 0,
                "top_return": round(float(d.avg_return_t5 or 0), 2),
                "has_backtest": True,
            })
        return history_data

    # 回退: 用推荐统计（标记为无回测数据）
    date_stats = session.query(
        DailyRecommendation.trade_date,
        func.count(DailyRecommendation.id).label("count"),
        func.avg(DailyRecommendation.total_score).label("avg_score"),
    ).group_by(DailyRecommendation.trade_date)\
     .order_by(DailyRecommendation.trade_date.desc())\
     .limit(30).all()

    return [{
        "date": str(d.trade_date),
        "total_recommended": d.count,
        "count": d.count,
        "avg_score": round(float(d.avg_score), 1) if d.avg_score else 0,
        "win_rate": 0,
        "avg_return": 0,
        "top_return": 0,
        "has_backtest": False,
    } for d in reversed(date_stats)]


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = Depends(get_db_dep)):
    trade_date = _get_latest_trade_date(session)
    recommendations = _build_recommendations(session, trade_date)
    industries = sorted(set(r["industry"] for r in recommendations if r["industry"]))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "today": str(trade_date) if trade_date else str(date.today()),
        "indices": _build_market_indices(),
        "sectors": json.dumps(_build_sectors(), ensure_ascii=False),
        "sankey": json.dumps(_build_sankey(session), ensure_ascii=False),
        "recommendations": recommendations,
        "sentiment": _build_sentiment(session),
        "industries_json": json.dumps(industries, ensure_ascii=False),
        "all_recommendations_json": json.dumps(recommendations, ensure_ascii=False),
    })


@app.get("/stock/{code}", response_class=HTMLResponse)
async def stock_detail(request: Request, code: str, session: Session = Depends(get_db_dep)):
    rec = session.query(DailyRecommendation).filter_by(
        stock_code=code
    ).order_by(DailyRecommendation.trade_date.desc()).first()

    if rec:
        sigs = json.loads(rec.signals_json) if rec.signals_json else {"bullish": [], "bearish": []}
        stock = {
            "code": rec.stock_code, "name": rec.stock_name,
            "total_score": rec.total_score,
            "technical_score": rec.technical_score or 0,
            "fundamental_score": rec.fundamental_score or 0,
            "money_flow_score": rec.money_flow_score or 0,
            "sentiment_score": rec.sentiment_score or 0,
            "close_price": rec.close_price or 0,
            "change_pct": rec.change_pct or 0,
            "risk_level": rec.risk_level or "中",
            "advice": _score_to_advice(rec.total_score),
            "bullish": sigs.get("bullish", []),
            "bearish": sigs.get("bearish", []),
            "warning": sigs.get("bearish", ["注意仓位控制"])[:1],
            "industry": rec.industry or "",
        }
    else:
        stock = {
            "code": code, "name": "未知", "total_score": 0,
            "technical_score": 0, "fundamental_score": 0,
            "money_flow_score": 0, "sentiment_score": 0,
            "close_price": 0, "change_pct": 0, "risk_level": "中",
            "advice": "无数据", "bullish": [], "bearish": [],
            "warning": [], "industry": "",
        }

    kline_data = _build_kline_data(code, session)
    fundamentals = _build_fundamentals(code, session)
    money_flow = _build_money_flow(code, session)
    analysis = _build_analysis(code, session)

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "today": str(date.today()),
        "stock": stock,
        "kline_json": json.dumps(kline_data["kline"], ensure_ascii=False),
        "ma5_json": json.dumps(kline_data["ma5"]),
        "ma10_json": json.dumps(kline_data["ma10"]),
        "ma20_json": json.dumps(kline_data["ma20"]),
        "ma60_json": json.dumps(kline_data["ma60"]),
        "boll_upper_json": json.dumps(kline_data["boll_upper"]),
        "boll_mid_json": json.dumps(kline_data["boll_mid"]),
        "boll_lower_json": json.dumps(kline_data["boll_lower"]),
        "dif_json": json.dumps(kline_data["dif"]),
        "dea_json": json.dumps(kline_data["dea"]),
        "macd_hist_json": json.dumps(kline_data["macd_hist"]),
        "rsi6_json": json.dumps(kline_data["rsi6"]),
        "rsi12_json": json.dumps(kline_data["rsi12"]),
        "rsi24_json": json.dumps(kline_data["rsi24"]),
        "kdj_k_json": json.dumps(kline_data["kdj_k"]),
        "kdj_d_json": json.dumps(kline_data["kdj_d"]),
        "kdj_j_json": json.dumps(kline_data["kdj_j"]),
        "vol_colors_json": json.dumps(kline_data["vol_colors"]),
        "fundamentals": fundamentals,
        "money_flow": money_flow,
        "analysis": analysis,
    })


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, session: Session = Depends(get_db_dep)):
    history_data = _build_history_data(session)
    return templates.TemplateResponse("history.html", {
        "request": request,
        "today": str(date.today()),
        "history_data": history_data,
        "history_json": json.dumps(history_data, ensure_ascii=False),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    weights = settings.get_weights_display()
    filters = {
        "exclude_st": settings.filter_st,
        "exclude_limit": True,
        "min_market_cap": settings.filter_min_market_cap,
        "max_turnover": settings.filter_max_turnover,
        "max_change_pct": settings.filter_max_change_pct,
        "min_days_listed": settings.filter_new_days,
    }
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "today": str(date.today()),
        "weights": weights,
        "filters": filters,
        "weights_json": json.dumps(weights, ensure_ascii=False),
        "filters_json": json.dumps(filters, ensure_ascii=False),
    })


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
async def api_dashboard(session: Session = Depends(get_db_dep)):
    return {
        "code": 0,
        "data": {
            "indices": _build_market_indices(),
            "sectors": _build_sectors(),
            "sankey": _build_sankey(session),
            "sentiment": _build_sentiment(session),
        },
    }


@app.get("/api/recommendation/{date_str}")
async def api_recommendation(date_str: str, session: Session = Depends(get_db_dep)):
    try:
        trade_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        trade_date = _get_latest_trade_date(session)

    recommendations = _build_recommendations(session, trade_date)
    return {
        "code": 0,
        "data": {
            "date": str(trade_date) if trade_date else "",
            "total": len(recommendations),
            "list": recommendations,
        },
    }


@app.get("/api/stock/{code}/technical")
async def api_stock_technical(code: str, session: Session = Depends(get_db_dep)):
    kline_data = _build_kline_data(code, session)
    analysis = _build_analysis(code, session)
    return {
        "code": 0,
        "data": {
            "kline": kline_data["kline"][-60:],
            "ma5": kline_data["ma5"][-60:],
            "ma10": kline_data["ma10"][-60:],
            "ma20": kline_data["ma20"][-60:],
            "ma60": kline_data["ma60"][-60:],
            "dif": kline_data["dif"][-60:],
            "dea": kline_data["dea"][-60:],
            "macd_hist": kline_data["macd_hist"][-60:],
            "rsi6": kline_data["rsi6"][-60:],
            "rsi12": kline_data["rsi12"][-60:],
            "analysis": analysis,
        },
    }


@app.get("/api/stock/{code}/fundamental")
async def api_stock_fundamental(code: str, session: Session = Depends(get_db_dep)):
    return {"code": 0, "data": _build_fundamentals(code, session)}


@app.get("/api/stock/{code}/money_flow")
async def api_stock_money_flow(code: str, session: Session = Depends(get_db_dep)):
    return {"code": 0, "data": _build_money_flow(code, session)}


@app.get("/api/stock/{code}/kline")
async def api_stock_kline(code: str, session: Session = Depends(get_db_dep),
                          period: str = "daily", count: int = 60):
    kline_data = _build_kline_data(code, session)
    return {
        "code": 0,
        "data": {
            "period": period,
            "count": min(count, len(kline_data["kline"])),
            "kline": kline_data["kline"][-count:],
            "ma5": kline_data["ma5"][-count:],
            "ma10": kline_data["ma10"][-count:],
            "ma20": kline_data["ma20"][-count:],
            "ma60": kline_data["ma60"][-count:],
            "vol_colors": kline_data["vol_colors"][-count:],
        },
    }


@app.get("/api/market/sectors")
async def api_market_sectors():
    return {"code": 0, "data": _build_sectors()}


@app.get("/api/market/money_flow")
async def api_market_money_flow(session: Session = Depends(get_db_dep)):
    return {"code": 0, "data": _build_sankey(session)}


@app.get("/api/market/sentiment")
async def api_market_sentiment(session: Session = Depends(get_db_dep)):
    return {"code": 0, "data": _build_sentiment(session)}


@app.get("/api/history/win_rate")
async def api_history_win_rate(session: Session = Depends(get_db_dep)):
    history_data = _build_history_data(session)
    return {"code": 0, "data": history_data}


@app.get("/api/search")
async def api_search(q: str = "", session: Session = Depends(get_db_dep)):
    if not q or len(q.strip()) == 0:
        return {"code": 0, "data": []}

    query = q.strip()
    trade_date = _get_latest_trade_date(session)
    if not trade_date:
        return {"code": 0, "data": []}

    # SQL LIKE 下推到数据库
    recs = session.query(DailyRecommendation).filter(
        DailyRecommendation.trade_date == trade_date,
        (DailyRecommendation.stock_code.like(f"%{query}%")) |
        (DailyRecommendation.stock_name.like(f"%{query}%"))
    ).limit(10).all()

    return {"code": 0, "data": [{
        "code": r.stock_code,
        "name": r.stock_name,
        "industry": r.industry or "",
        "total_score": r.total_score,
        "change_pct": r.change_pct or 0,
    } for r in recs]}


@app.post("/api/settings/weights")
async def api_settings_weights(request: Request):
    body = await request.json()
    weights = {
        "technical": body.get("technical", 30),
        "fundamental": body.get("fundamental", 25),
        "money_flow": body.get("money_flow", 25),
        "sentiment": body.get("sentiment", 20),
    }
    settings.save_user_settings(weights)
    return {"code": 0, "message": "权重已更新并保存", "data": settings.get_weights_display()}


@app.post("/api/task/run")
async def api_task_run():
    from app.scheduler.jobs import run_daily_pipeline, get_pipeline_status
    import threading

    status = get_pipeline_status()
    if status["running"]:
        return {
            "code": 1,
            "message": "任务正在运行中，请勿重复触发",
            "data": status,
        }

    t = threading.Thread(target=run_daily_pipeline, daemon=True)
    t.start()
    return {
        "code": 0,
        "message": "任务已启动",
        "data": {
            "task_id": f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "status": "running",
            "started_at": datetime.now().isoformat(),
        },
    }


@app.get("/api/task/status")
async def api_task_status():
    from app.scheduler.jobs import get_pipeline_status
    return {"code": 0, "data": get_pipeline_status()}


@app.get("/api/health")
async def health(session: Session = Depends(get_db_dep)):
    trade_date = _get_latest_trade_date(session)
    rec_count = session.query(DailyRecommendation).count()
    result_count = session.query(RecommendationResult).count()
    return {
        "status": "ok",
        "version": "3.1.0",
        "latest_date": str(trade_date) if trade_date else None,
        "total_recommendations": rec_count,
        "total_backtest_results": result_count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
