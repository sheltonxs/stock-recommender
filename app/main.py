"""A股智选 - 每日股票推荐系统 (原型版 v2)"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="A股智选")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TODAY = "2026-02-20"

# ---------------------------------------------------------------------------
# 100-Stock Pool  (code, name, industry, approx_price)
# ---------------------------------------------------------------------------

STOCK_POOL = [
    # 白酒 (5)
    ("600519", "贵州茅台", "白酒", 1856.00),
    ("000858", "五粮液", "白酒", 168.30),
    ("000568", "泸州老窖", "白酒", 178.50),
    ("002304", "洋河股份", "白酒", 98.60),
    ("600809", "山西汾酒", "白酒", 215.80),
    # 银行 (5)
    ("600036", "招商银行", "银行", 38.25),
    ("601166", "兴业银行", "银行", 18.92),
    ("600000", "浦发银行", "银行", 8.65),
    ("601398", "工商银行", "银行", 5.82),
    ("601288", "农业银行", "银行", 4.35),
    # 新能源车 (5)
    ("002594", "比亚迪", "新能源车", 285.40),
    ("601238", "广汽集团", "新能源车", 9.85),
    ("000625", "长安汽车", "新能源车", 15.70),
    ("002466", "天齐锂业", "新能源车", 42.30),
    ("300014", "亿纬锂能", "新能源车", 52.80),
    # 半导体 (5)
    ("002049", "紫光国微", "半导体", 78.60),
    ("688981", "中芯国际", "半导体", 58.90),
    ("603501", "韦尔股份", "半导体", 95.20),
    ("688008", "澜起科技", "半导体", 68.50),
    ("002371", "北方华创", "半导体", 320.00),
    # 医药生物 (5)
    ("603259", "药明康德", "医药生物", 62.40),
    ("300760", "迈瑞医疗", "医药生物", 298.50),
    ("300122", "智飞生物", "医药生物", 42.80),
    ("600276", "恒瑞医药", "医药生物", 48.60),
    ("000661", "长春高新", "医药生物", 165.00),
    # 人工智能/算力 (5)
    ("002230", "科大讯飞", "人工智能", 58.90),
    ("300496", "中科创达", "人工智能", 82.50),
    ("688111", "金山办公", "人工智能", 285.00),
    ("300474", "景嘉微", "人工智能", 98.20),
    ("002415", "海康威视", "人工智能", 35.60),
    # 食品饮料 (5)
    ("603288", "海天味业", "食品饮料", 42.15),
    ("600887", "伊利股份", "食品饮料", 30.20),
    ("002714", "牧原股份", "食品饮料", 42.50),
    ("600600", "青岛啤酒", "食品饮料", 72.80),
    ("000895", "双汇发展", "食品饮料", 28.50),
    # 家电 (4)
    ("000333", "美的集团", "家电", 68.50),
    ("000651", "格力电器", "家电", 42.30),
    ("002032", "苏泊尔", "家电", 52.60),
    ("600690", "海尔智家", "家电", 28.90),
    # 军工 (4)
    ("600893", "航发动力", "军工", 42.80),
    ("600760", "中航沈飞", "军工", 52.30),
    ("002179", "中航光电", "军工", 45.60),
    ("601989", "中国重工", "军工", 5.28),
    # 光伏 (4)
    ("601012", "隆基绿能", "光伏", 28.75),
    ("002129", "TCL中环", "光伏", 15.80),
    ("688599", "天合光能", "光伏", 22.50),
    ("601615", "明阳智能", "光伏", 18.30),
    # 锂电池 (4)
    ("300750", "宁德时代", "锂电池", 245.60),
    ("002460", "赣锋锂业", "锂电池", 38.50),
    ("300769", "德方纳米", "锂电池", 52.60),
    ("688005", "容百科技", "锂电池", 42.30),
    # 证券 (4)
    ("601211", "国泰君安", "证券", 16.80),
    ("600030", "中信证券", "证券", 22.50),
    ("601688", "华泰证券", "证券", 18.90),
    ("600999", "招商证券", "证券", 15.20),
    # 保险 (3)
    ("601318", "中国平安", "保险", 52.80),
    ("601628", "中国人寿", "保险", 38.50),
    ("601601", "中国太保", "保险", 28.60),
    # 房地产 (4)
    ("000002", "万科A", "房地产", 9.85),
    ("001979", "招商蛇口", "房地产", 12.30),
    ("600048", "保利发展", "房地产", 10.50),
    ("000069", "华侨城A", "房地产", 5.20),
    # 有色金属 (4)
    ("601899", "紫金矿业", "有色金属", 15.80),
    ("600362", "江西铜业", "有色金属", 22.50),
    ("600489", "中金黄金", "有色金属", 12.60),
    ("000831", "中国稀土", "有色金属", 18.90),
    # 化工 (4)
    ("600309", "万华化学", "化工", 82.50),
    ("002601", "龙蟒佰利", "化工", 18.30),
    ("600426", "华鲁恒升", "化工", 28.50),
    ("000792", "盐湖股份", "化工", 22.80),
    # 通信设备 (4)
    ("300308", "中际旭创", "通信设备", 145.80),
    ("000063", "中兴通讯", "通信设备", 32.50),
    ("600498", "烽火通信", "通信设备", 22.80),
    ("300502", "新易盛", "通信设备", 128.50),
    # 汽车零部件 (4)
    ("600660", "福耀玻璃", "汽车零部件", 52.30),
    ("002920", "德赛西威", "汽车零部件", 128.50),
    ("601799", "星宇股份", "汽车零部件", 98.60),
    ("603786", "科博达", "汽车零部件", 72.30),
    # 消费电子 (4)
    ("002475", "立讯精密", "消费电子", 38.50),
    ("601138", "工业富联", "消费电子", 22.80),
    ("002241", "歌尔股份", "消费电子", 25.60),
    ("300433", "蓝思科技", "消费电子", 18.90),
    # 煤炭 (3)
    ("601088", "中国神华", "煤炭", 35.20),
    ("600188", "兖矿能源", "煤炭", 28.50),
    ("601898", "中煤能源", "煤炭", 12.80),
    # 钢铁 (3)
    ("600019", "宝钢股份", "钢铁", 7.25),
    ("000709", "河钢股份", "钢铁", 3.15),
    ("600010", "包钢股份", "钢铁", 1.85),
    # 电力 (3)
    ("600900", "长江电力", "电力", 28.50),
    ("003816", "中国广核", "电力", 5.20),
    ("600886", "国投电力", "电力", 18.30),
    # 建筑 (3)
    ("601668", "中国建筑", "建筑", 6.50),
    ("601390", "中国中铁", "建筑", 7.85),
    ("601186", "中国铁建", "建筑", 8.20),
    # 传媒 (2)
    ("002027", "分众传媒", "传媒", 7.20),
    ("300413", "芒果超媒", "传媒", 32.50),
    # 纺织服装 (2)
    ("600398", "海澜之家", "纺织服装", 8.50),
    ("002832", "比音勒芬", "纺织服装", 28.60),
    # 农林牧渔 (2)
    ("300498", "温氏股份", "农林牧渔", 18.50),
    ("002311", "海大集团", "农林牧渔", 42.30),
]

# ---------------------------------------------------------------------------
# Signal Pools
# ---------------------------------------------------------------------------

BULLISH_SIGNALS = [
    "均线多头排列", "MACD水上金叉", "MACD金叉", "量比放量上涨",
    "OBV持续上升", "北向资金净买入", "主力连续净流入", "BOLL中上轨运行",
    "KDJ金叉", "RSI健康区间", "ROE行业领先", "PE低于行业均值",
    "营收增速>20%", "毛利率提升", "板块热度前5", "机构增持评级",
    "股息率较高", "行业景气度上行",
]

BEARISH_SIGNALS = [
    "RSI接近超买", "KDJ超买区", "成交量萎缩", "PE偏高",
    "均线趋于粘合", "板块整体偏弱", "量价背离", "MACD顶背离",
    "换手率偏高", "短期涨幅过大", "负债率偏高", "毛利率下滑",
]

# ---------------------------------------------------------------------------
# Generate 100 Recommendations
# ---------------------------------------------------------------------------

def generate_all_recommendations(pool, seed=42):
    """Generate scored recommendations for every stock in pool."""
    rng = random.Random(seed)
    recs = []
    for code, name, industry, approx_price in pool:
        tech = rng.randint(30, 98)
        fund = rng.randint(25, 98)
        money = rng.randint(20, 95)
        sent = rng.randint(20, 90)
        total = round(tech * 0.3 + fund * 0.25 + money * 0.25 + sent * 0.2, 1)
        change_pct = round(rng.uniform(-4, 5), 2)

        if total >= 80:
            risk = "低"
        elif total >= 60:
            risk = "中"
        else:
            risk = "高"

        if total >= 80:
            advice = "强烈看多"
        elif total >= 70:
            advice = "偏多"
        elif total >= 55:
            advice = "中性偏多"
        elif total >= 40:
            advice = "中性"
        else:
            advice = "偏空"

        n_bull = rng.randint(2, 4)
        n_bear = rng.randint(1, 2)
        bullish = rng.sample(BULLISH_SIGNALS, min(n_bull, len(BULLISH_SIGNALS)))
        bearish = rng.sample(BEARISH_SIGNALS, min(n_bear, len(BEARISH_SIGNALS)))

        recs.append({
            "rank": 0,
            "code": code,
            "name": name,
            "industry": industry,
            "total_score": total,
            "technical_score": tech,
            "fundamental_score": fund,
            "money_flow_score": money,
            "sentiment_score": sent,
            "close_price": round(approx_price * (1 + change_pct / 100), 2),
            "change_pct": change_pct,
            "risk_level": risk,
            "advice": advice,
            "bullish": bullish,
            "bearish": bearish,
            "warning": [bearish[0] if bearish else "注意仓位控制"],
        })

    recs.sort(key=lambda r: r["total_score"], reverse=True)
    for i, r in enumerate(recs, 1):
        r["rank"] = i
    return recs


RECOMMENDATIONS = generate_all_recommendations(STOCK_POOL, seed=42)

# Quick-lookup dict
_REC_BY_CODE = {r["code"]: r for r in RECOMMENDATIONS}

# ---------------------------------------------------------------------------
# Generate Fundamentals
# ---------------------------------------------------------------------------

_INDUSTRY_PE = {
    "白酒": 32.1, "银行": 5.5, "新能源车": 28.5, "半导体": 55.2,
    "医药生物": 28.5, "人工智能": 45.8, "食品饮料": 32.5, "家电": 18.5,
    "军工": 42.0, "光伏": 22.3, "锂电池": 35.2, "证券": 22.0,
    "保险": 12.5, "房地产": 8.5, "有色金属": 15.0, "化工": 18.0,
    "通信设备": 45.8, "汽车零部件": 25.0, "消费电子": 30.0, "煤炭": 8.0,
    "钢铁": 10.0, "电力": 15.0, "建筑": 7.5, "传媒": 35.0,
    "纺织服装": 20.0, "农林牧渔": 25.0,
}


def generate_fundamentals(code, seed=None):
    """Generate fundamental data for a stock."""
    s = seed if seed is not None else hash(code) % 10000
    rng = random.Random(s)
    rec = _REC_BY_CODE.get(code)
    industry = rec["industry"] if rec else "其他"
    return {
        "pe": round(rng.uniform(5, 65), 1),
        "pb": round(rng.uniform(0.8, 15), 1),
        "roe": round(rng.uniform(5, 30), 1),
        "gross_margin": round(rng.uniform(10, 92), 1),
        "net_margin": round(rng.uniform(3, 50), 1),
        "revenue_yoy": round(rng.uniform(-15, 55), 1),
        "profit_yoy": round(rng.uniform(-20, 70), 1),
        "debt_ratio": round(rng.uniform(10, 92), 1),
        "market_cap": round(rng.uniform(200, 25000), 0),
        "dividend_yield": round(rng.uniform(0.1, 5), 1),
        "industry_pe": _INDUSTRY_PE.get(industry, 20.0),
    }


# Pre-generate fundamentals for all stocks
STOCK_FUNDAMENTALS = {code: generate_fundamentals(code) for code, _, _, _ in STOCK_POOL}

# ---------------------------------------------------------------------------
# Generate Money Flow
# ---------------------------------------------------------------------------

def generate_money_flow(code, seed=None):
    """Generate 5 days of money flow data."""
    s = seed if seed is not None else hash(code) % 10000
    rng = random.Random(s)
    dates = ["02-20", "02-19", "02-18", "02-17", "02-14"]
    result = []
    for d in dates:
        main = round(rng.uniform(-20000, 30000), 0)
        north = round(rng.uniform(-5000, 10000), 0)
        super_large = round(rng.uniform(-15000, 20000), 0)
        large = round(main - super_large, 0)
        medium = round(rng.uniform(-8000, 5000), 0)
        small = round(-(main + medium), 0)
        result.append({
            "date": d,
            "main": int(main),
            "north": int(north),
            "super_large": int(super_large),
            "large": int(large),
            "medium": int(medium),
            "small": int(small),
        })
    return result


# Pre-generate money flow for all stocks
STOCK_MONEY_FLOW = {code: generate_money_flow(code) for code, _, _, _ in STOCK_POOL}

# ---------------------------------------------------------------------------
# Generate Analysis  (key="signals", NOT "items" -- Jinja2 conflict)
# ---------------------------------------------------------------------------

def generate_analysis(stock, seed=None):
    """Generate technical analysis with 4 sections."""
    s = seed if seed is not None else hash(stock["code"]) % 10000
    rng = random.Random(s)

    section_titles = ["趋势研判", "量能分析", "通道位置", "超买超卖"]
    signal_types = ["bullish", "warning", "neutral"]

    trend_signals = [
        ("均线多头排列 (MA5>MA10>MA20>MA60)，趋势强势", "bullish"),
        ("MACD水上金叉，红柱放大，做多动能增强", "bullish"),
        ("MA20上行斜率加速，中期趋势向好", "bullish"),
        ("均线空头排列，趋势偏弱", "warning"),
        ("MACD绿柱缩短，空头动能减弱", "neutral"),
        ("短期均线拐头向上，有企稳迹象", "bullish"),
    ]
    volume_signals = [
        ("量比放大，量价配合良好", "bullish"),
        ("OBV持续上升，场外资金流入", "bullish"),
        ("成交量萎缩，观望情绪浓厚", "warning"),
        ("换手率适中，筹码锁定良好", "neutral"),
        ("地量出现，可能接近变盘点", "neutral"),
    ]
    channel_signals = [
        ("BOLL中上轨运行，通道开口向上", "bullish"),
        ("BOLL中轨附近震荡，方向待选择", "neutral"),
        ("价格触及BOLL下轨，存在超跌反弹需求", "bullish"),
        ("BOLL通道收窄，即将变盘", "warning"),
        ("短期压力位与支撑位明确", "neutral"),
    ]
    overbought_signals = [
        ("RSI健康区间运行，仍有上行空间", "bullish"),
        ("RSI接近超买区，注意回调风险", "warning"),
        ("KDJ金叉有效，动能向上", "bullish"),
        ("KDJ超买区域，短线谨慎", "warning"),
        ("CCI强势区间运行", "bullish"),
        ("RSI底背离，反弹信号", "bullish"),
    ]

    all_pools = [trend_signals, volume_signals, channel_signals, overbought_signals]
    sections = []
    for i, title in enumerate(section_titles):
        pool = all_pools[i]
        n = rng.randint(2, 3)
        picked = rng.sample(pool, min(n, len(pool)))
        sections.append({
            "title": title,
            "signals": [{"text": text, "type": tp} for text, tp in picked],
        })

    advice_pool = [
        "偏多操作，可关注回踩均线附近买入机会",
        "短线观望为主，等待方向确认",
        "逢低可适量布局，注意控制仓位",
        "趋势向好，可持股待涨",
        "震荡格局，高抛低吸为主",
    ]
    stop_loss_pool = [
        "跌破MA20考虑止损",
        "跌破BOLL中轨减仓",
        "跌破前低止损",
        "下跌放量注意止损",
    ]

    total = stock.get("total_score", 50)
    if total >= 70:
        summary = "偏多"
    elif total >= 50:
        summary = "中性"
    else:
        summary = "偏空"

    return {
        "technical_summary": summary,
        "sections": sections,
        "advice": rng.choice(advice_pool),
        "stop_loss": rng.choice(stop_loss_pool),
    }


# Pre-generate analysis for all stocks
STOCK_ANALYSIS = {r["code"]: generate_analysis(r) for r in RECOMMENDATIONS}

# ---------------------------------------------------------------------------
# History Data  (10 trading days)
# ---------------------------------------------------------------------------

def _generate_history_data(seed=42):
    rng = random.Random(seed)
    data = []
    dt = datetime(2026, 2, 20)
    for i in range(10):
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        win_rate = round(rng.uniform(55, 72), 1)
        avg_ret = round(rng.uniform(0.5, 2.5), 2)
        top_ret = round(avg_ret + rng.uniform(2, 8), 2)
        data.append({
            "date": dt.strftime("%Y-%m-%d"),
            "win_rate": win_rate,
            "avg_return": avg_ret,
            "top_return": top_ret,
            "total_recommended": 100,
        })
        dt -= timedelta(days=1)
    return data


HISTORY_DATA = _generate_history_data()

# ---------------------------------------------------------------------------
# Settings Defaults
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "technical": 30,
    "fundamental": 25,
    "money_flow": 25,
    "sentiment": 20,
}

DEFAULT_FILTERS = {
    "exclude_st": True,
    "min_market_cap": 20,
    "max_turnover": 20,
    "min_days_listed": 60,
    "exclude_limit": True,
}

# ---------------------------------------------------------------------------
# Market Data  (unchanged from v1)
# ---------------------------------------------------------------------------

MARKET_INDICES = [
    {"name": "上证指数", "code": "000001.SH", "price": 3245.67, "change": 39.52, "change_pct": 1.23, "volume": "4526亿"},
    {"name": "深证成指", "code": "399001.SZ", "price": 10876.43, "change": 94.21, "change_pct": 0.87, "volume": "5832亿"},
    {"name": "创业板指", "code": "399006.SZ", "price": 2156.34, "change": 45.32, "change_pct": 2.15, "volume": "2841亿"},
    {"name": "北向资金", "code": "NORTH", "price": 52.3, "change": 52.3, "change_pct": 0, "volume": "连续3日净流入", "is_north": True},
]

SECTORS = [
    {"name": "半导体", "change_pct": 3.21, "amount": 285.6, "leader": "中芯国际"},
    {"name": "新能源车", "change_pct": 2.85, "amount": 342.1, "leader": "比亚迪"},
    {"name": "白酒", "change_pct": 1.98, "amount": 198.3, "leader": "贵州茅台"},
    {"name": "光伏", "change_pct": 1.75, "amount": 156.2, "leader": "隆基绿能"},
    {"name": "人工智能", "change_pct": 1.62, "amount": 278.9, "leader": "科大讯飞"},
    {"name": "消费电子", "change_pct": 1.45, "amount": 134.5, "leader": "立讯精密"},
    {"name": "军工", "change_pct": 1.23, "amount": 167.8, "leader": "中航沈飞"},
    {"name": "医药生物", "change_pct": 0.87, "amount": 212.4, "leader": "药明康德"},
    {"name": "锂电池", "change_pct": 0.65, "amount": 189.7, "leader": "宁德时代"},
    {"name": "汽车零部件", "change_pct": 0.42, "amount": 98.3, "leader": "福耀玻璃"},
    {"name": "通信设备", "change_pct": 0.21, "amount": 87.6, "leader": "中兴通讯"},
    {"name": "保险", "change_pct": 0.08, "amount": 65.4, "leader": "中国平安"},
    {"name": "银行", "change_pct": -0.35, "amount": 178.9, "leader": "招商银行"},
    {"name": "食品饮料", "change_pct": -0.52, "amount": 76.5, "leader": "海天味业"},
    {"name": "房地产", "change_pct": -1.23, "amount": 145.6, "leader": "万科A"},
    {"name": "钢铁", "change_pct": -1.56, "amount": 54.3, "leader": "宝钢股份"},
    {"name": "煤炭", "change_pct": -1.87, "amount": 67.8, "leader": "中国神华"},
    {"name": "纺织服装", "change_pct": -2.12, "amount": 32.1, "leader": "海澜之家"},
    {"name": "传媒", "change_pct": -0.78, "amount": 45.6, "leader": "分众传媒"},
    {"name": "农林牧渔", "change_pct": -0.95, "amount": 38.9, "leader": "牧原股份"},
]

SANKEY_DATA = {
    "nodes": [
        {"name": "北向资金"},
        {"name": "主力资金"},
        {"name": "融资余额"},
        {"name": "半导体"},
        {"name": "新能源车"},
        {"name": "白酒"},
        {"name": "人工智能"},
        {"name": "医药生物"},
        {"name": "光伏"},
        {"name": "军工"},
        {"name": "锂电池"},
    ],
    "links": [
        {"source": "北向资金", "target": "半导体", "value": 18.5},
        {"source": "北向资金", "target": "白酒", "value": 12.3},
        {"source": "北向资金", "target": "新能源车", "value": 8.7},
        {"source": "北向资金", "target": "医药生物", "value": 6.5},
        {"source": "北向资金", "target": "人工智能", "value": 6.3},
        {"source": "主力资金", "target": "半导体", "value": 15.2},
        {"source": "主力资金", "target": "新能源车", "value": 8.5},
        {"source": "主力资金", "target": "人工智能", "value": 7.8},
        {"source": "主力资金", "target": "光伏", "value": 4.0},
        {"source": "主力资金", "target": "军工", "value": 3.5},
        {"source": "融资余额", "target": "白酒", "value": 5.2},
        {"source": "融资余额", "target": "锂电池", "value": 4.8},
        {"source": "融资余额", "target": "新能源车", "value": 3.5},
        {"source": "融资余额", "target": "半导体", "value": 3.0},
    ],
}

SENTIMENT = {
    "fear_greed_index": 62,
    "label": "偏贪婪",
    "advance": 2847,
    "decline": 1923,
    "flat": 312,
    "limit_up": 45,
    "limit_down": 12,
    "total_amount": "10358亿",
    "avg_turnover": 1.82,
}


# ---------------------------------------------------------------------------
# K-Line & Indicator Generation  (unchanged from v1)
# ---------------------------------------------------------------------------

def _ema(data: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(data)
    if len(data) < period:
        return result
    k = 2 / (period + 1)
    result[period - 1] = sum(data[:period]) / period
    for i in range(period, len(data)):
        result[i] = data[i] * k + result[i - 1] * (1 - k)
    return result


def _sma(data: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(data)
    for i in range(period - 1, len(data)):
        result[i] = sum(data[i - period + 1 : i + 1]) / period
    return result


def generate_kline(days: int = 180, start_price: float = 150.0, seed: int = 42) -> dict:
    rng = random.Random(seed)
    kline = []
    price = start_price
    dt = datetime(2025, 7, 1)

    for _ in range(days):
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        drift = rng.gauss(0.0008, 0.022)
        o = round(price * (1 + rng.gauss(0, 0.004)), 2)
        c = round(price * (1 + drift), 2)
        h = round(max(o, c) * (1 + abs(rng.gauss(0, 0.008))), 2)
        low = round(min(o, c) * (1 - abs(rng.gauss(0, 0.008))), 2)
        vol = int(rng.randint(80000, 250000) * (1 + abs(drift) * 15))
        kline.append({"time": dt.strftime("%Y-%m-%d"), "open": o, "high": h, "low": low, "close": c, "volume": vol})
        price = c
        dt += timedelta(days=1)

    closes = [k["close"] for k in kline]
    highs = [k["high"] for k in kline]
    lows = [k["low"] for k in kline]

    # Moving averages
    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    # BOLL(20,2)
    boll_mid = _sma(closes, 20)
    boll_upper: list[float | None] = [None] * len(closes)
    boll_lower: list[float | None] = [None] * len(closes)
    for i in range(19, len(closes)):
        window = closes[i - 19 : i + 1]
        std = (sum((x - boll_mid[i]) ** 2 for x in window) / 20) ** 0.5
        boll_upper[i] = round(boll_mid[i] + 2 * std, 2)
        boll_lower[i] = round(boll_mid[i] - 2 * std, 2)

    # MACD(12,26,9)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if ema12[i] is not None and ema26[i] is not None:
            dif[i] = round(ema12[i] - ema26[i], 4)
    dif_vals = [v for v in dif if v is not None]
    dea_raw = _ema(dif_vals, 9)
    dea: list[float | None] = [None] * len(closes)
    offset = len(closes) - len(dif_vals)
    for i, v in enumerate(dea_raw):
        if v is not None:
            dea[offset + i] = round(v, 4)
    macd_hist: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if dif[i] is not None and dea[i] is not None:
            macd_hist[i] = round((dif[i] - dea[i]) * 2, 4)

    # RSI(6,12,24)
    def _rsi(data: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * len(data)
        for i in range(period, len(data)):
            gains, losses = [], []
            for j in range(i - period + 1, i + 1):
                delta = data[j] - data[j - 1]
                gains.append(max(delta, 0))
                losses.append(max(-delta, 0))
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = round(100 - 100 / (1 + rs), 2)
        return result

    rsi6 = _rsi(closes, 6)
    rsi12 = _rsi(closes, 12)
    rsi24 = _rsi(closes, 24)

    # KDJ(9,3,3)
    kdj_k: list[float | None] = [None] * len(closes)
    kdj_d: list[float | None] = [None] * len(closes)
    kdj_j: list[float | None] = [None] * len(closes)
    prev_k, prev_d = 50.0, 50.0
    for i in range(8, len(closes)):
        h9 = max(highs[i - 8 : i + 1])
        l9 = min(lows[i - 8 : i + 1])
        rsv = ((closes[i] - l9) / (h9 - l9) * 100) if h9 != l9 else 50
        k = 2 / 3 * prev_k + 1 / 3 * rsv
        d = 2 / 3 * prev_d + 1 / 3 * k
        j = 3 * k - 2 * d
        kdj_k[i] = round(k, 2)
        kdj_d[i] = round(d, 2)
        kdj_j[i] = round(j, 2)
        prev_k, prev_d = k, d

    # Volume colors (up=red, down=green per A-stock convention)
    vol_colors = []
    for k in kline:
        vol_colors.append("#EF4444" if k["close"] >= k["open"] else "#22C55E")

    return {
        "kline": kline,
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "boll_upper": boll_upper, "boll_mid": boll_mid, "boll_lower": boll_lower,
        "dif": dif, "dea": dea, "macd_hist": macd_hist,
        "rsi6": rsi6, "rsi12": rsi12, "rsi24": rsi24,
        "kdj_k": kdj_k, "kdj_d": kdj_d, "kdj_j": kdj_j,
        "vol_colors": vol_colors,
    }


# ---------------------------------------------------------------------------
# Pre-generate K-line data for TOP 30 stocks only (performance)
# ---------------------------------------------------------------------------

STOCK_KLINES: dict[str, dict] = {}
for _rec in RECOMMENDATIONS[:30]:
    STOCK_KLINES[_rec["code"]] = generate_kline(
        days=180,
        start_price=_rec["close_price"] * random.uniform(0.75, 0.95),
        seed=hash(_rec["code"]) % 10000,
    )


def _get_kline(code: str) -> dict:
    """Get kline data for a stock; generate on-demand if not cached."""
    if code not in STOCK_KLINES:
        rec = _REC_BY_CODE.get(code)
        price = rec["close_price"] if rec else 50.0
        STOCK_KLINES[code] = generate_kline(
            days=180,
            start_price=price * random.uniform(0.75, 0.95),
            seed=hash(code) % 10000,
        )
    return STOCK_KLINES[code]


# ---------------------------------------------------------------------------
# Helper: unique industries for filter dropdown
# ---------------------------------------------------------------------------

_ALL_INDUSTRIES = sorted(set(r["industry"] for r in RECOMMENDATIONS))


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "today": TODAY,
        "indices": MARKET_INDICES,
        "sectors": json.dumps(SECTORS, ensure_ascii=False),
        "sankey": json.dumps(SANKEY_DATA, ensure_ascii=False),
        "recommendations": RECOMMENDATIONS,
        "sentiment": SENTIMENT,
        "industries_json": json.dumps(_ALL_INDUSTRIES, ensure_ascii=False),
        "all_recommendations_json": json.dumps(RECOMMENDATIONS, ensure_ascii=False),
    })


@app.get("/stock/{code}", response_class=HTMLResponse)
async def stock_detail(request: Request, code: str):
    stock = _REC_BY_CODE.get(code)
    if stock is None:
        stock = {
            "code": code, "name": "未知", "total_score": 0, "technical_score": 0,
            "fundamental_score": 0, "money_flow_score": 0, "sentiment_score": 0,
            "close_price": 0, "change_pct": 0, "risk_level": "中", "advice": "无数据",
            "bullish": [], "bearish": [], "warning": [], "industry": "",
        }

    kline_data = _get_kline(code)
    fundamentals = STOCK_FUNDAMENTALS.get(code, generate_fundamentals(code))
    money_flow = STOCK_MONEY_FLOW.get(code, generate_money_flow(code))
    analysis = STOCK_ANALYSIS.get(code, generate_analysis(stock))

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "today": TODAY,
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
async def history_page(request: Request):
    return templates.TemplateResponse("history.html", {
        "request": request,
        "today": TODAY,
        "history_data": HISTORY_DATA,
        "history_json": json.dumps(HISTORY_DATA, ensure_ascii=False),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "today": TODAY,
        "weights": DEFAULT_WEIGHTS,
        "filters": DEFAULT_FILTERS,
        "weights_json": json.dumps(DEFAULT_WEIGHTS, ensure_ascii=False),
        "filters_json": json.dumps(DEFAULT_FILTERS, ensure_ascii=False),
    })


# ---------------------------------------------------------------------------
# API Routes  (all return JSON)
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
async def api_dashboard():
    return {
        "code": 0,
        "data": {
            "indices": MARKET_INDICES,
            "sectors": SECTORS,
            "sankey": SANKEY_DATA,
            "sentiment": SENTIMENT,
        },
    }


@app.get("/api/recommendation/{date}")
async def api_recommendation(date: str):
    return {
        "code": 0,
        "data": {
            "date": date,
            "total": len(RECOMMENDATIONS),
            "list": RECOMMENDATIONS,
        },
    }


@app.get("/api/stock/{code}/technical")
async def api_stock_technical(code: str):
    kline_data = _get_kline(code)
    analysis = STOCK_ANALYSIS.get(code)
    if analysis is None:
        rec = _REC_BY_CODE.get(code, {"code": code, "total_score": 50})
        analysis = generate_analysis(rec)
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
async def api_stock_fundamental(code: str):
    fund = STOCK_FUNDAMENTALS.get(code, generate_fundamentals(code))
    return {"code": 0, "data": fund}


@app.get("/api/stock/{code}/money_flow")
async def api_stock_money_flow(code: str):
    mf = STOCK_MONEY_FLOW.get(code, generate_money_flow(code))
    return {"code": 0, "data": mf}


@app.get("/api/stock/{code}/kline")
async def api_stock_kline(code: str, period: str = "daily", count: int = 60):
    kline_data = _get_kline(code)
    kline_list = kline_data["kline"]
    count = min(count, len(kline_list))
    return {
        "code": 0,
        "data": {
            "period": period,
            "count": count,
            "kline": kline_list[-count:],
            "ma5": kline_data["ma5"][-count:],
            "ma10": kline_data["ma10"][-count:],
            "ma20": kline_data["ma20"][-count:],
            "ma60": kline_data["ma60"][-count:],
            "vol_colors": kline_data["vol_colors"][-count:],
        },
    }


@app.get("/api/market/sectors")
async def api_market_sectors():
    return {"code": 0, "data": SECTORS}


@app.get("/api/market/money_flow")
async def api_market_money_flow():
    return {"code": 0, "data": SANKEY_DATA}


@app.get("/api/market/sentiment")
async def api_market_sentiment():
    return {"code": 0, "data": SENTIMENT}


@app.get("/api/history/win_rate")
async def api_history_win_rate():
    return {"code": 0, "data": HISTORY_DATA}


@app.get("/api/search")
async def api_search(q: str = ""):
    if not q or len(q.strip()) == 0:
        return {"code": 0, "data": []}
    query = q.strip().lower()
    results = []
    for r in RECOMMENDATIONS:
        if query in r["code"].lower() or query in r["name"].lower():
            results.append({
                "code": r["code"],
                "name": r["name"],
                "industry": r["industry"],
                "total_score": r["total_score"],
                "change_pct": r["change_pct"],
            })
        if len(results) >= 10:
            break
    return {"code": 0, "data": results}


@app.post("/api/settings/weights")
async def api_settings_weights(request: Request):
    body = await request.json()
    # In a real app this would persist; here just echo back
    weights = {
        "technical": body.get("technical", DEFAULT_WEIGHTS["technical"]),
        "fundamental": body.get("fundamental", DEFAULT_WEIGHTS["fundamental"]),
        "money_flow": body.get("money_flow", DEFAULT_WEIGHTS["money_flow"]),
        "sentiment": body.get("sentiment", DEFAULT_WEIGHTS["sentiment"]),
    }
    return {"code": 0, "message": "权重已更新", "data": weights}


@app.post("/api/task/run")
async def api_task_run(request: Request):
    return {
        "code": 0,
        "message": "任务已启动",
        "data": {
            "task_id": "task_20260220_001",
            "status": "running",
            "started_at": datetime.now().isoformat(),
        },
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0-prototype"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
