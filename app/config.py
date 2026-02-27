"""A股智选 - 配置管理"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "user_settings.json"


class Settings:
    """应用配置，可通过环境变量覆盖"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.db_url = f"sqlite:///{self.data_dir / 'stock.db'}"

        self.stock_pool_size = 100
        self.pool_multiplier = 2  # 采集池 = 推荐数 × 倍率 = 200

        self.weight_technical = float(os.getenv("WEIGHT_TECH", "0.30"))
        self.weight_fundamental = float(os.getenv("WEIGHT_FUND", "0.25"))
        self.weight_money_flow = float(os.getenv("WEIGHT_MONEY", "0.25"))
        self.weight_sentiment = float(os.getenv("WEIGHT_SENT", "0.20"))

        self.akshare_delay = 1.5
        self.akshare_retry = 4
        self.kline_days = 250

        self.filter_st = True
        self.filter_new_days = 60
        self.filter_max_turnover = 20.0
        self.filter_min_market_cap = 20.0
        self.filter_max_change_pct = 9.5

        self.schedule_collect_hour = 15
        self.schedule_collect_minute = 30

        self.pipeline_max_retries = 2
        self.pipeline_retry_delay_minutes = 30

        # 启动时加载用户设置
        self._load_user_settings()

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load_user_settings(self):
        """从 JSON 文件加载用户自定义权重"""
        settings_path = self.data_dir / "user_settings.json"
        if not settings_path.exists():
            return
        try:
            data = json.loads(settings_path.read_text())
            self.weight_technical = data.get("weight_technical", self.weight_technical)
            self.weight_fundamental = data.get("weight_fundamental", self.weight_fundamental)
            self.weight_money_flow = data.get("weight_money_flow", self.weight_money_flow)
            self.weight_sentiment = data.get("weight_sentiment", self.weight_sentiment)
            logger.info(f"已加载用户权重设置: tech={self.weight_technical} "
                        f"fund={self.weight_fundamental} money={self.weight_money_flow} "
                        f"sent={self.weight_sentiment}")
        except Exception as e:
            logger.warning(f"加载用户设置失败: {e}")

    def save_user_settings(self, weights: dict):
        """保存用户自定义权重到 JSON 文件

        Args:
            weights: {"technical": 30, "fundamental": 25, ...} (百分比整数)
        """
        self.ensure_dirs()
        data = {
            "weight_technical": weights.get("technical", 30) / 100,
            "weight_fundamental": weights.get("fundamental", 25) / 100,
            "weight_money_flow": weights.get("money_flow", 25) / 100,
            "weight_sentiment": weights.get("sentiment", 20) / 100,
        }
        # 更新内存中的值
        self.weight_technical = data["weight_technical"]
        self.weight_fundamental = data["weight_fundamental"]
        self.weight_money_flow = data["weight_money_flow"]
        self.weight_sentiment = data["weight_sentiment"]

        settings_path = self.data_dir / "user_settings.json"
        settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info(f"用户权重已保存: {data}")

    def get_weights_display(self) -> dict:
        """返回百分比整数格式的权重（供前端显示）"""
        return {
            "technical": int(self.weight_technical * 100),
            "fundamental": int(self.weight_fundamental * 100),
            "money_flow": int(self.weight_money_flow * 100),
            "sentiment": int(self.weight_sentiment * 100),
        }


settings = Settings()
