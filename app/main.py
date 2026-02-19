"""A股智选 - 每日股票推荐系统 (v3 - 真实数据版)"""

import json
import logging
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import get_session
from app.models.database import (
    StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="A股智选")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Helper: build template data from DB
# ---------------------------------------------------------------------------

def _get_latest_trade_date(session) -> date | None:
    row = session.query(DailyRecommendation.trade_date)\
        .order_by(DailyRecommendation.trade_date.desc()).first()
    return row[0] if row else None


def _build_recommendations(session, trade_date) -> list[dict]:
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


def _build_market_indices(session) -> list[dict]:
    """Build market index cards -- use cached snapshot or defaults"""
    return [
        {"name": "上证指数", "code": "000001", "price": 0, "change": 0, "change_pct": 0, "volume": "0亿"},
        {"name": "深证成指", "code": "399001", "price": 0, "change": 0, "change_pct": 0, "volume": "0亿"},
        {"name": "创业板指", "code": "399006", "price": 0, "change": 0, "change_pct": 0, "volume": "0亿"},
        {"name": "北向资金", "code": "NORTH", "price": 0, "change": 0, "change_pct": 0, "volume": "0亿"},
    ]


def _build_sectors(session) -> list[dict]:
    """Build sector heatmap data from recommendations"""
    trade_date = _get_latest_trade_date(session)
    recs = session.query(DailyRecommendation).filter(
        DailyRecommendation.trade_date == trade_date
    ).all() if trade_date else []

    industry_map = {}
    for r in recs:
        ind = r.industry or "其他"
        if ind not in industry_map:
            industry_map[ind] = {"name": ind, "value": 0, "change_pct": 0, "count": 0}
        industry_map[ind]["count"] += 1
        industry_map[ind]["value"] += abs(r.change_pct or 0)
        industry_map[ind]["change_pct"] += (r.change_pct or 0)

    sectors = []
    for ind, data in industry_map.items():
        n = data["count"] or 1
        sectors.append({
            "name": ind,
            "value": round(data["value"] / n, 2),
            "change_pct": round(data["change_pct"] / n, 2),
        })
    return sectors if sectors else [{"name": "暂无数据", "value": 0, "change_pct": 0}]


def _build_sankey(session) -> dict:
    """Build sankey data from recommendations"""
    trade_date = _get_latest_trade_date(session)
    recs = session.query(DailyRecommendation).filter(
        DailyRecommendation.trade_date == trade_date
    ).all() if trade_date else []

    sources = set()
    targets = set()
    links = []

    # Group by industry and aggregate
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


def _build_sentiment(session) -> dict:
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


def _build_kline_data(code: str, session) -> dict:
    """Build K-line + indicator data for detail page"""
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

    # Calculate indicators using the TechnicalAnalyzer
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

    return {
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


def _build_fundamentals(code: str, session) -> dict:
    """Build fundamental data dict for detail page.

    Template uses: pe, pb, roe, gross_margin, net_margin, revenue_yoy,
    profit_yoy, debt_ratio, market_cap, industry_pe.
    All numeric values default to 0 so Jinja2 comparisons never fail.
    """
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


def _build_money_flow(code: str, session) -> list[dict]:
    """Build money flow data for detail page.

    Template uses: date, main, north, super_large, large, medium, small.
    """
    rows = session.query(StockMoneyFlow).filter_by(
        stock_code=code
    ).order_by(StockMoneyFlow.trade_date.desc()).limit(5).all()

    return [{
        "date": str(r.trade_date)[5:],  # "MM-DD" format
        "main": int(r.main_net_inflow or 0),
        "north": 0,  # Not stored per-stock; placeholder
        "super_large": int(r.super_large_net or 0),
        "large": int(r.large_net or 0),
        "medium": int(r.medium_net or 0),
        "small": int(r.small_net or 0),
    } for r in rows]


def _build_analysis(code: str, session) -> dict:
    """Build analysis data for detail page.

    Template uses: technical_summary, sections (list of {title, signals}),
    advice, stop_loss.
    """
    rec = session.query(DailyRecommendation).filter_by(
        stock_code=code
    ).order_by(DailyRecommendation.trade_date.desc()).first()

    if not rec:
        return {
            "technical_summary": "中性",
            "sections": [],
            "advice": "暂无数据",
            "stop_loss": "暂无数据",
        }

    sigs = json.loads(rec.signals_json) if rec.signals_json else {"bullish": [], "bearish": []}
    bullish = sigs.get("bullish", [])
    bearish = sigs.get("bearish", [])

    # Build sections from signals
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

    # If no categorized signals, put them all in a generic section
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

    return {
        "technical_summary": summary,
        "sections": sections,
        "advice": "偏多操作，可关注回踩均线附近买入机会" if total >= 60 else "短线观望为主，等待方向确认",
        "stop_loss": "跌破MA20考虑止损" if total >= 50 else "跌破前低止损",
    }


# ---------------------------------------------------------------------------
# Weights / Filters defaults (for settings page)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "technical": settings.weight_technical,
    "fundamental": settings.weight_fundamental,
    "money_flow": settings.weight_money_flow,
    "sentiment": settings.weight_sentiment,
}

DEFAULT_FILTERS = {
    "exclude_st": settings.filter_st,
    "min_market_cap": settings.filter_min_market_cap,
    "max_turnover": settings.filter_max_turnover,
    "max_change_pct": settings.filter_max_change_pct,
    "min_days": settings.filter_new_days,
}


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = get_session()
    try:
        trade_date = _get_latest_trade_date(session)
        recommendations = _build_recommendations(session, trade_date)
        industries = sorted(set(r["industry"] for r in recommendations if r["industry"]))

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "today": str(trade_date) if trade_date else str(date.today()),
            "indices": _build_market_indices(session),
            "sectors": json.dumps(_build_sectors(session), ensure_ascii=False),
            "sankey": json.dumps(_build_sankey(session), ensure_ascii=False),
            "recommendations": recommendations,
            "sentiment": _build_sentiment(session),
            "industries_json": json.dumps(industries, ensure_ascii=False),
            "all_recommendations_json": json.dumps(recommendations, ensure_ascii=False),
        })
    finally:
        session.close()


@app.get("/stock/{code}", response_class=HTMLResponse)
async def stock_detail(request: Request, code: str):
    session = get_session()
    try:
        # Get recommendation data for header
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
    finally:
        session.close()


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    session = get_session()
    try:
        # Get distinct trade dates with recommendation counts
        from sqlalchemy import func
        date_stats = session.query(
            DailyRecommendation.trade_date,
            func.count(DailyRecommendation.id).label("count"),
            func.avg(DailyRecommendation.total_score).label("avg_score"),
        ).group_by(DailyRecommendation.trade_date)\
         .order_by(DailyRecommendation.trade_date.desc())\
         .limit(30).all()

        history_data = [{
            "date": str(d.trade_date),
            "count": d.count,
            "avg_score": round(float(d.avg_score), 1) if d.avg_score else 0,
            "win_rate": 0,  # Would need next-day data to calculate
        } for d in reversed(date_stats)]

        return templates.TemplateResponse("history.html", {
            "request": request,
            "today": str(date.today()),
            "history_data": history_data,
            "history_json": json.dumps(history_data, ensure_ascii=False),
        })
    finally:
        session.close()


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "today": str(date.today()),
        "weights": DEFAULT_WEIGHTS,
        "filters": DEFAULT_FILTERS,
        "weights_json": json.dumps(DEFAULT_WEIGHTS, ensure_ascii=False),
        "filters_json": json.dumps(DEFAULT_FILTERS, ensure_ascii=False),
    })


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
async def api_dashboard():
    session = get_session()
    try:
        return {
            "code": 0,
            "data": {
                "indices": _build_market_indices(session),
                "sectors": _build_sectors(session),
                "sankey": _build_sankey(session),
                "sentiment": _build_sentiment(session),
            },
        }
    finally:
        session.close()


@app.get("/api/recommendation/{date_str}")
async def api_recommendation(date_str: str):
    session = get_session()
    try:
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
    finally:
        session.close()


@app.get("/api/stock/{code}/technical")
async def api_stock_technical(code: str):
    session = get_session()
    try:
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
    finally:
        session.close()


@app.get("/api/stock/{code}/fundamental")
async def api_stock_fundamental(code: str):
    session = get_session()
    try:
        return {"code": 0, "data": _build_fundamentals(code, session)}
    finally:
        session.close()


@app.get("/api/stock/{code}/money_flow")
async def api_stock_money_flow(code: str):
    session = get_session()
    try:
        return {"code": 0, "data": _build_money_flow(code, session)}
    finally:
        session.close()


@app.get("/api/stock/{code}/kline")
async def api_stock_kline(code: str, period: str = "daily", count: int = 60):
    session = get_session()
    try:
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
    finally:
        session.close()


@app.get("/api/market/sectors")
async def api_market_sectors():
    session = get_session()
    try:
        return {"code": 0, "data": _build_sectors(session)}
    finally:
        session.close()


@app.get("/api/market/money_flow")
async def api_market_money_flow():
    session = get_session()
    try:
        return {"code": 0, "data": _build_sankey(session)}
    finally:
        session.close()


@app.get("/api/market/sentiment")
async def api_market_sentiment():
    session = get_session()
    try:
        return {"code": 0, "data": _build_sentiment(session)}
    finally:
        session.close()


@app.get("/api/history/win_rate")
async def api_history_win_rate():
    session = get_session()
    try:
        from sqlalchemy import func
        stats = session.query(
            DailyRecommendation.trade_date,
            func.avg(DailyRecommendation.total_score).label("avg_score"),
        ).group_by(DailyRecommendation.trade_date)\
         .order_by(DailyRecommendation.trade_date.desc()).limit(30).all()

        return {"code": 0, "data": [
            {"date": str(s.trade_date), "avg_score": round(float(s.avg_score), 1)}
            for s in reversed(stats)
        ]}
    finally:
        session.close()


@app.get("/api/search")
async def api_search(q: str = ""):
    if not q or len(q.strip()) == 0:
        return {"code": 0, "data": []}

    session = get_session()
    try:
        query = q.strip().lower()
        trade_date = _get_latest_trade_date(session)
        if not trade_date:
            return {"code": 0, "data": []}

        recs = session.query(DailyRecommendation).filter_by(
            trade_date=trade_date
        ).all()

        results = []
        for r in recs:
            if query in r.stock_code.lower() or query in r.stock_name.lower():
                results.append({
                    "code": r.stock_code,
                    "name": r.stock_name,
                    "industry": r.industry or "",
                    "total_score": r.total_score,
                    "change_pct": r.change_pct or 0,
                })
            if len(results) >= 10:
                break
        return {"code": 0, "data": results}
    finally:
        session.close()


@app.post("/api/settings/weights")
async def api_settings_weights(request: Request):
    body = await request.json()
    weights = {
        "technical": body.get("technical", DEFAULT_WEIGHTS["technical"]),
        "fundamental": body.get("fundamental", DEFAULT_WEIGHTS["fundamental"]),
        "money_flow": body.get("money_flow", DEFAULT_WEIGHTS["money_flow"]),
        "sentiment": body.get("sentiment", DEFAULT_WEIGHTS["sentiment"]),
    }
    return {"code": 0, "message": "权重已更新", "data": weights}


@app.post("/api/task/run")
async def api_task_run():
    from app.scheduler.jobs import run_daily_pipeline
    import threading
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


@app.get("/api/health")
async def health():
    session = get_session()
    try:
        trade_date = _get_latest_trade_date(session)
        rec_count = session.query(DailyRecommendation).count()
        return {
            "status": "ok",
            "version": "3.0.0",
            "latest_date": str(trade_date) if trade_date else None,
            "total_recommendations": rec_count,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.scheduler.jobs import run_daily_pipeline
        scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        scheduler.add_job(
            run_daily_pipeline, "cron",
            hour=settings.schedule_collect_hour,
            minute=settings.schedule_collect_minute,
            day_of_week="mon-fri",
            id="daily_pipeline",
        )
        scheduler.start()
        logger.info("APScheduler 启动成功, 每日 15:30 执行")
    except Exception as e:
        logger.warning(f"调度器启动失败 (可忽略): {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
