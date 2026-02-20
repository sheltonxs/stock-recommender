"""A股智选 - TTL 内存缓存

线程安全的简单缓存，避免每次 Dashboard 请求都调 AKShare API。
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """线程安全的 TTL 内存缓存"""

    def __init__(self):
        self._data: dict[str, tuple] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: int = 300):
        """获取缓存值，过期返回 None

        Args:
            key: 缓存键
            ttl: 缓存有效期（秒），默认 5 分钟
        """
        with self._lock:
            if key in self._data:
                val, ts = self._data[key]
                if time.time() - ts < ttl:
                    return val
                # 过期清理
                del self._data[key]
            return None

    def set(self, key: str, value):
        """设置缓存值"""
        with self._lock:
            self._data[key] = (value, time.time())

    def invalidate(self, key: str | None = None):
        """清除缓存

        Args:
            key: 指定键清除，None 清除全部
        """
        with self._lock:
            if key:
                self._data.pop(key, None)
            else:
                self._data.clear()
                logger.debug("缓存已全部清除")

    def get_or_set(self, key: str, fn, ttl: int = 300):
        """获取缓存，未命中则调用 fn 并缓存结果

        Args:
            key: 缓存键
            fn: 缓存未命中时的回调函数
            ttl: 缓存有效期（秒）
        """
        val = self.get(key, ttl)
        if val is not None:
            return val
        val = fn()
        self.set(key, val)
        return val


# 全局缓存实例
cache = TTLCache()


def is_trading_time() -> bool:
    """判断当前是否为交易时间（工作日 9:15-15:30）"""
    from datetime import datetime
    now = datetime.now()
    # 周末
    if now.weekday() >= 5:
        return False
    # 交易时段 9:15 - 15:30
    t = now.hour * 100 + now.minute
    return 915 <= t <= 1530


def get_cache_ttl(trading_ttl: int = 300, non_trading_ttl: int = 1800) -> int:
    """根据交易时间返回不同 TTL

    Args:
        trading_ttl: 交易时间 TTL（秒），默认 5 分钟
        non_trading_ttl: 非交易时间 TTL（秒），默认 30 分钟
    """
    return trading_ttl if is_trading_time() else non_trading_ttl
