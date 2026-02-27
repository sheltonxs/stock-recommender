"""行情数据采集: K线 + 实时快照 + 涨停池"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, stock_market
from app.models.database import StockDaily

logger = logging.getLogger(__name__)

SNAPSHOT_CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "snapshot_cache.json"

_KLINE_COL_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "change_pct",
    "换手率": "turnover_rate",
}


class MarketCollector(BaseCollector):

    def _map_kline_row(self, code: str, name: str, row: dict) -> dict:
        mapped = {"stock_code": code, "stock_name": name}
        for cn_col, en_col in _KLINE_COL_MAP.items():
            val = row.get(cn_col)
            if en_col == "trade_date":
                if isinstance(val, str):
                    val = datetime.strptime(val, "%Y-%m-%d").date()
                elif hasattr(val, "date") and not isinstance(val, date):
                    val = val.date()
            mapped[en_col] = val
        return mapped

    def _map_spot_row(self, row: dict) -> dict:
        return {
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": row.get("最新价"),
            "change_pct": row.get("涨跌幅"),
            "volume": row.get("成交量"),
            "amount": row.get("成交额"),
            "turnover_rate": row.get("换手率"),
            "pe_ttm": row.get("市盈率-动态"),
            "pb": row.get("市净率"),
            "market_cap": row.get("总市值"),
            "float_market_cap": row.get("流通市值"),
            "volume_ratio": row.get("量比"),
        }

    def collect_kline(self, code: str, name: str, session: Session,
                      days: int = 250) -> int:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        df = self._call_ak(
            "stock_zh_a_hist",
            symbol=code, period="daily",
            start_date=start_date, end_date=end_date,
            adjust="qfq",
        )
        if df is None or df.empty:
            logger.warning(f"[{code}] K线数据为空")
            return 0

        count = 0
        for _, row in df.iterrows():
            mapped = self._map_kline_row(code, name, row.to_dict())
            exists = session.query(StockDaily).filter_by(
                stock_code=code, trade_date=mapped["trade_date"]
            ).first()
            if exists:
                continue
            session.add(StockDaily(**mapped))
            count += 1

        session.commit()
        logger.info(f"[{code} {name}] 新增 {count} 条K线")
        return count

    def collect_snapshot(self) -> pd.DataFrame:
        """获取全A快照，三级降级: Tier1 push2实时 → Tier2 comment_em(24h) → Tier3 文件缓存"""
        # Tier 1: push2 实时快照
        try:
            df = self._call_ak("stock_zh_a_spot_em")
            if df is not None and not df.empty:
                self._save_snapshot_cache(df)
                return df
        except Exception as e:
            logger.warning(f"Tier1 实时快照失败: {e}")

        # Tier 2: stock_comment_em (datacenter-web, 24h可用)
        try:
            df = self._collect_snapshot_night()
            if df is not None and not df.empty:
                logger.info(f"Tier2 comment_em 快照获取成功: {len(df)} 条")
                self._save_snapshot_cache(df)
                return df
        except Exception as e:
            logger.warning(f"Tier2 comment_em 快照失败: {e}")

        # Tier 3: 文件缓存
        return self._load_snapshot_cache()

    def _collect_snapshot_night(self) -> pd.DataFrame:
        """夜间快照源: stock_comment_em (datacenter-web, 24h可用)"""
        df = self._call_ak("stock_comment_em")
        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {}
        for col in df.columns:
            if "代码" in col:
                col_map[col] = "代码"
            elif "名称" in col:
                col_map[col] = "名称"
            elif "最新价" in col or "收盘价" in col:
                col_map[col] = "最新价"
            elif "涨跌幅" in col:
                col_map[col] = "涨跌幅"
            elif "换手率" in col:
                col_map[col] = "换手率"
            elif "市盈率" in col:
                col_map[col] = "市盈率-动态"

        if col_map:
            df = df.rename(columns=col_map)

        # 过滤无效行
        if "最新价" in df.columns:
            df = df[pd.to_numeric(df["最新价"], errors="coerce") > 0]

        if len(df) < 100:
            logger.warning(f"comment_em 有效行不足: {len(df)}")
            return pd.DataFrame()

        return df

    def _save_snapshot_cache(self, df: pd.DataFrame):
        try:
            SNAPSHOT_CACHE.parent.mkdir(parents=True, exist_ok=True)
            cache = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "data": df.to_dict(orient="records"),
            }
            SNAPSHOT_CACHE.write_text(json.dumps(cache, ensure_ascii=False, default=str))
            logger.info(f"快照已缓存: {len(df)} 条")
        except Exception as e:
            logger.warning(f"快照缓存写入失败: {e}")

    def _load_snapshot_cache(self) -> pd.DataFrame:
        if not SNAPSHOT_CACHE.exists():
            logger.warning("无快照缓存文件")
            return pd.DataFrame()
        try:
            cache = json.loads(SNAPSHOT_CACHE.read_text())
            cached_date = cache.get("date", "unknown")
            df = pd.DataFrame(cache["data"])
            logger.info(f"已加载缓存快照 ({cached_date}), {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"缓存快照加载失败: {e}")
            return pd.DataFrame()

    def collect_zt_pool(self, trade_date: str) -> pd.DataFrame:
        df = self._call_ak("stock_zt_pool_em", date=trade_date)
        return df if df is not None else pd.DataFrame()

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        return self._collect_batch(
            stock_list, session,
            lambda code, name, sess: self.collect_kline(code, name, sess),
            label="K线",
        )
