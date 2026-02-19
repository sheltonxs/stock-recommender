"""市场情绪数据采集: 板块资金、涨停池、北向资金"""

import logging
from datetime import datetime

import pandas as pd

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class SentimentCollector(BaseCollector):

    def collect_sector_flow(self) -> pd.DataFrame:
        df = self._call_ak("stock_sector_fund_flow_rank",
                           indicator="今日", sector_type="行业资金流")
        return df if df is not None else pd.DataFrame()

    def collect_board_names(self) -> pd.DataFrame:
        df = self._call_ak("stock_board_industry_name_em")
        return df if df is not None else pd.DataFrame()

    def collect_zt_pool(self, trade_date: str) -> pd.DataFrame:
        df = self._call_ak("stock_zt_pool_em", date=trade_date)
        return df if df is not None else pd.DataFrame()

    def collect_north_flow(self) -> pd.DataFrame:
        try:
            df = self._call_ak("stock_hsgt_north_net_flow_in_em",
                               indicator="沪股通")
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"北向资金接口失败: {e}")
            return pd.DataFrame()

    def collect(self) -> dict:
        return {
            "sector_flow": self.collect_sector_flow(),
            "boards": self.collect_board_names(),
            "zt_pool": self.collect_zt_pool(datetime.now().strftime("%Y%m%d")),
            "north_flow": self.collect_north_flow(),
        }
