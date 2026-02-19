import time
import pytest
from unittest.mock import patch
from app.collectors.base import BaseCollector, stock_market


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
