"""Tests for all four analyzers: technical, fundamental, money_flow, sentiment."""

import numpy as np
import pandas as pd

from app.analyzers.technical import TechnicalAnalyzer
from app.analyzers.fundamental import FundamentalAnalyzer
from app.analyzers.money_flow import MoneyFlowAnalyzer
from app.analyzers.sentiment import SentimentAnalyzer


# ------------------------------------------------------------------
# Helper: generate synthetic K-line data
# ------------------------------------------------------------------

def _make_kline_df(days=120, trend="up"):
    np.random.seed(42)
    dates = pd.date_range("2025-10-01", periods=days, freq="B")
    base = 100.0
    closes = []
    for i in range(days):
        if trend == "up":
            base *= 1 + np.random.uniform(0, 0.02)
        elif trend == "down":
            base *= 1 - np.random.uniform(0, 0.02)
        else:
            base *= 1 + np.random.uniform(-0.01, 0.01)
        closes.append(round(base, 2))

    opens = [c * np.random.uniform(0.995, 1.005) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.0, 1.02) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.98, 1.0) for o, c in zip(opens, closes)]
    volumes = [int(np.random.uniform(50000, 200000)) for _ in range(days)]

    return pd.DataFrame({
        "trade_date": dates,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "amount": [v * c for v, c in zip(volumes, closes)],
        "turnover_rate": [np.random.uniform(0.5, 5.0) for _ in range(days)],
        "change_pct": [0] + [round((closes[i] - closes[i-1]) / closes[i-1] * 100, 2)
                              for i in range(1, days)],
    })


# ====================================================================
# Technical Analyzer Tests
# ====================================================================

def test_score_returns_0_to_100():
    df = _make_kline_df(120, "up")
    analyzer = TechnicalAnalyzer()
    result = analyzer.score(df)
    assert 0 <= result["total"] <= 100
    assert "trend" in result
    assert "volume" in result
    assert "channel" in result
    assert "overbought" in result
    assert isinstance(result["signals"], list)


def test_uptrend_scores_higher():
    analyzer = TechnicalAnalyzer()
    np.random.seed(42)
    up_df = _make_kline_df(120, "up")
    np.random.seed(42)
    down_df = _make_kline_df(120, "down")
    up_score = analyzer.score(up_df)["total"]
    down_score = analyzer.score(down_df)["total"]
    assert up_score > down_score, f"Up {up_score} should > Down {down_score}"


def test_get_latest_indicators():
    df = _make_kline_df(120, "up")
    analyzer = TechnicalAnalyzer()
    indicators = analyzer.get_latest_indicators(df)
    assert "ma5" in indicators
    assert "macd_dif" in indicators
    assert "rsi_12" in indicators
    assert indicators["ma5"] is not None


# ====================================================================
# Fundamental Analyzer Tests
# ====================================================================

def test_fundamental_score_range():
    data = {
        "pe_ttm": 25.0, "pb": 3.0, "roe": 22.0,
        "gross_margin": 65.0, "net_margin": 35.0,
        "revenue_yoy": 25.0, "profit_yoy": 30.0,
        "debt_ratio": 35.0, "current_ratio": 2.5,
        "operating_cashflow": 50.0,
    }
    analyzer = FundamentalAnalyzer()
    result = analyzer.score(data, industry_avg_pe=32.0)
    assert 0 <= result["total"] <= 100
    assert "valuation" in result


def test_low_pe_high_roe_scores_higher():
    analyzer = FundamentalAnalyzer()
    good = {"pe_ttm": 10, "pb": 1.5, "roe": 25, "gross_margin": 70,
            "net_margin": 40, "revenue_yoy": 35, "profit_yoy": 45,
            "debt_ratio": 30, "current_ratio": 3.0, "operating_cashflow": 60}
    bad = {"pe_ttm": 100, "pb": 8, "roe": 5, "gross_margin": 15,
           "net_margin": 3, "revenue_yoy": -5, "profit_yoy": -10,
           "debt_ratio": 85, "current_ratio": 0.5, "operating_cashflow": -10}
    assert analyzer.score(good, 32)["total"] > analyzer.score(bad, 32)["total"]


# ====================================================================
# Money Flow Analyzer Tests
# ====================================================================

def test_money_flow_score():
    rows = [
        {"main_net_inflow": 20000, "main_net_ratio": 8, "super_large_net": 12000},
        {"main_net_inflow": 15000, "main_net_ratio": 6, "super_large_net": 8000},
        {"main_net_inflow": 25000, "main_net_ratio": 12, "super_large_net": 18000},
    ]
    analyzer = MoneyFlowAnalyzer()
    result = analyzer.score(rows)
    assert 0 <= result["total"] <= 100
    assert len(result["signals"]) > 0


# ====================================================================
# Sentiment Analyzer Tests
# ====================================================================

def test_sentiment_hot_sector():
    boards_df = pd.DataFrame({
        "板块名称": ["白酒", "银行", "半导体", "医药", "新能源"],
        "涨跌幅": [3.5, 2.1, 1.8, 1.5, 1.2],
    })
    zt_pool_df = pd.DataFrame({"代码": ["600519"], "连板数": [1]})
    sector_flow_df = pd.DataFrame({
        "名称": ["白酒", "银行", "半导体"],
    })

    analyzer = SentimentAnalyzer()
    result = analyzer.score("600519", "白酒", sector_flow_df, zt_pool_df, boards_df)
    assert result["total"] > 0
    assert any("板块" in s for s in result["signals"])
