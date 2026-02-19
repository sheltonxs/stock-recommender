"""A股智选 - 配置管理"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings:
    """应用配置，可通过环境变量覆盖"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.db_url = f"sqlite:///{self.data_dir / 'stock.db'}"

        self.stock_pool_size = 100

        self.weight_technical = float(os.getenv("WEIGHT_TECH", "0.30"))
        self.weight_fundamental = float(os.getenv("WEIGHT_FUND", "0.25"))
        self.weight_money_flow = float(os.getenv("WEIGHT_MONEY", "0.25"))
        self.weight_sentiment = float(os.getenv("WEIGHT_SENT", "0.20"))

        self.akshare_delay = 0.4
        self.akshare_retry = 3
        self.kline_days = 250

        self.filter_st = True
        self.filter_new_days = 60
        self.filter_max_turnover = 20.0
        self.filter_min_market_cap = 20.0
        self.filter_max_change_pct = 9.5

        self.schedule_collect_hour = 15
        self.schedule_collect_minute = 30

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
