"""采集基类 - 限速、重试、日志"""

import random
import time
import logging

import akshare as ak

logger = logging.getLogger(__name__)


class BaseCollector:

    CIRCUIT_BREAK_THRESHOLD = 5  # 连续失败N次触发熔断

    def __init__(self, delay: float = 0.4, retry: int = 3):
        self.delay = delay
        self.retry = retry
        self._last_call = 0.0
        self._consecutive_failures = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        # 连续失败时自动加大延迟
        adaptive_delay = self.delay + (self._consecutive_failures * 0.5)
        # 添加随机抖动避免被检测
        jitter = random.uniform(0.1, 0.5)
        wait = adaptive_delay + jitter - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _call_ak_raw(self, func_name: str, **kwargs):
        fn = getattr(ak, func_name)
        return fn(**kwargs)

    def _call_ak(self, func_name: str, **kwargs):
        last_err = None
        for attempt in range(1, self.retry + 1):
            try:
                self._rate_limit()
                result = self._call_ak_raw(func_name, **kwargs)
                logger.debug(f"[{func_name}] 成功 (第{attempt}次)")
                self._consecutive_failures = max(0, self._consecutive_failures - 1)
                return result
            except Exception as e:
                last_err = e
                self._consecutive_failures += 1
                logger.warning(f"[{func_name}] 第{attempt}次失败: {e}")
                if attempt < self.retry:
                    backoff = 3.0 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    time.sleep(backoff)
        raise last_err

    def _collect_batch(self, stock_list, session, collect_fn, label=""):
        """批量采集，带熔断机制

        Args:
            stock_list: [(code, name), ...]
            session: SQLAlchemy session
            collect_fn: callable(code, name, session) -> int
            label: 日志标签
        """
        total = 0
        consecutive_fails = 0
        for code, name in stock_list:
            try:
                n = collect_fn(code, name, session)
                total += n
                consecutive_fails = 0
            except Exception as e:
                consecutive_fails += 1
                logger.error(f"[{code}] {label}采集失败: {e}")
                if consecutive_fails >= self.CIRCUIT_BREAK_THRESHOLD:
                    logger.error(
                        f"连续{consecutive_fails}次失败，触发熔断，"
                        f"停止{label}采集(已完成{total}条)"
                    )
                    break
        logger.info(f"{label}采集完成, 共 {total} 条")
        return total

    def collect(self):
        raise NotImplementedError


def stock_market(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    return "sz"
