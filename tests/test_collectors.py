import time
from datetime import date as date_type

import pytest
from unittest.mock import patch
from app.collectors.base import BaseCollector, stock_market
from app.collectors.market import MarketCollector
from app.collectors.fundamental import FundamentalCollector
from app.collectors.money_flow import MoneyFlowCollector


class DummyCollector(BaseCollector):
    def collect(self):
        return self._call_ak("dummy_func", arg1="test")


def test_rate_limiting():
    c = DummyCollector(delay=0.3)
    with patch.object(BaseCollector, "_call_ak_raw", return_value="ok"):
        t0 = time.time()
        c._call_ak("f1")
        c._call_ak("f2")
        elapsed = time.time() - t0
        assert elapsed >= 0.25


def test_retry_on_failure():
    c = DummyCollector(delay=0.1, retry=3)
    call_count = 0

    def flaky(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("timeout")
        return "success"

    with patch.object(BaseCollector, "_call_ak_raw", side_effect=flaky):
        result = c._call_ak("f1")
        assert result == "success"
        assert call_count == 3


def test_stock_market():
    assert stock_market("600519") == "sh"
    assert stock_market("000858") == "sz"
    assert stock_market("300750") == "sz"
    assert stock_market("688981") == "sh"


# --- MarketCollector tests ---

def test_parse_kline_row():
    raw_row = {
        "日期": "2026-02-20", "开盘": 168.5, "收盘": 170.3,
        "最高": 172.5, "最低": 167.0, "成交量": 85000,
        "成交额": 1450000000.0, "振幅": 3.27,
        "涨跌幅": 1.35, "涨跌额": 2.3, "换手率": 1.82,
    }
    c = MarketCollector.__new__(MarketCollector)
    result = c._map_kline_row("000858", "五粮液", raw_row)
    assert result["stock_code"] == "000858"
    assert result["close"] == 170.3
    assert result["trade_date"] == date_type(2026, 2, 20)


def test_parse_spot_row():
    raw_row = {
        "代码": "000858", "名称": "五粮液", "最新价": 170.3,
        "涨跌幅": 1.35, "成交量": 85000, "成交额": 1450000000,
        "换手率": 1.82, "市盈率-动态": 28.5, "市净率": 5.2,
        "总市值": 6600e8, "流通市值": 6200e8, "量比": 1.2,
    }
    c = MarketCollector.__new__(MarketCollector)
    result = c._map_spot_row(raw_row)
    assert result["code"] == "000858"
    assert result["pe_ttm"] == 28.5


# --- FundamentalCollector tests ---

def test_map_financial_row():
    raw = {
        "日期": "2025-09-30",
        "净资产收益率(%)": 22.5,
        "主营业务利润率(%)": 68.2,
        "销售净利率(%)": 35.8,
        "资产负债率(%)": 32.5,
        "流动比率": 2.8,
    }
    c = FundamentalCollector.__new__(FundamentalCollector)
    result = c._map_financial_row("000858", raw)
    assert result["stock_code"] == "000858"
    assert result["roe"] == 22.5
    assert result["debt_ratio"] == 32.5


# --- MoneyFlowCollector tests ---

def test_map_fund_flow_row():
    raw = {
        "日期": "2026-02-20",
        "主力净流入-净额": 23500.0,
        "主力净流入-净占比": 8.5,
        "超大单净流入-净额": 15000.0,
        "大单净流入-净额": 8500.0,
        "中单净流入-净额": -5000.0,
        "小单净流入-净额": -18500.0,
    }
    c = MoneyFlowCollector.__new__(MoneyFlowCollector)
    result = c._map_flow_row("000858", raw)
    assert result["main_net_inflow"] == 23500.0
    assert result["super_large_net"] == 15000.0
