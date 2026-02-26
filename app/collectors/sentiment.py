"""市场情绪数据采集: 板块资金、涨停池、北向资金"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

BOARD_CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "board_cache.json"


class SentimentCollector(BaseCollector):

    def collect_sector_flow(self) -> pd.DataFrame:
        df = self._call_ak("stock_sector_fund_flow_rank",
                           indicator="今日", sector_type="行业资金流")
        return df if df is not None else pd.DataFrame()

    def collect_board_names(self) -> pd.DataFrame:
        """获取板块列表，API失败时从文件缓存加载"""
        try:
            df = self._call_ak("stock_board_industry_name_em")
            if df is not None and not df.empty:
                self._save_board_cache(df)
                return df
        except Exception as e:
            logger.warning(f"板块API失败，尝试加载缓存: {e}")

        return self._load_board_cache()

    def _save_board_cache(self, df: pd.DataFrame):
        try:
            BOARD_CACHE.parent.mkdir(parents=True, exist_ok=True)
            cache = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "data": df.to_dict(orient="records"),
            }
            BOARD_CACHE.write_text(json.dumps(cache, ensure_ascii=False, default=str))
            logger.info(f"板块缓存已保存: {len(df)} 条")
        except Exception as e:
            logger.warning(f"板块缓存写入失败: {e}")

    def _load_board_cache(self) -> pd.DataFrame:
        if not BOARD_CACHE.exists():
            logger.warning("无板块缓存文件")
            return pd.DataFrame()
        try:
            cache = json.loads(BOARD_CACHE.read_text())
            cached_date = cache.get("date", "unknown")
            df = pd.DataFrame(cache["data"])
            logger.info(f"已加载板块缓存 ({cached_date}), {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"板块缓存加载失败: {e}")
            return pd.DataFrame()

    def collect_zt_pool(self, trade_date: str) -> pd.DataFrame:
        df = self._call_ak("stock_zt_pool_em", date=trade_date)
        return df if df is not None else pd.DataFrame()

    def collect_north_flow(self) -> pd.DataFrame:
        """北向资金历史数据 (datacenter-web, 24h可用)"""
        try:
            df = self._call_ak("stock_hsgt_hist_em", symbol="北向资金")
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"北向资金接口失败: {e}")
            return pd.DataFrame()

    def collect(self) -> dict:
        result = {}
        for key, fn in [
            ("sector_flow", self.collect_sector_flow),
            ("boards", self.collect_board_names),
            ("zt_pool", lambda: self.collect_zt_pool(datetime.now().strftime("%Y%m%d"))),
            ("north_flow", self.collect_north_flow),
        ]:
            try:
                result[key] = fn()
            except Exception as e:
                logger.warning(f"情绪数据[{key}]采集失败(降级为空): {e}")
                result[key] = pd.DataFrame()
        return result
