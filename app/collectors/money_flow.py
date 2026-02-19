"""资金流向采集"""

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, stock_market
from app.models.database import StockMoneyFlow

logger = logging.getLogger(__name__)


class MoneyFlowCollector(BaseCollector):

    def _map_flow_row(self, code: str, row: dict) -> dict:
        date_str = str(row.get("日期", ""))
        try:
            trade_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            trade_date = date.today()

        return {
            "stock_code": code,
            "trade_date": trade_date,
            "main_net_inflow": row.get("主力净流入-净额"),
            "main_net_ratio": row.get("主力净流入-净占比"),
            "super_large_net": row.get("超大单净流入-净额"),
            "large_net": row.get("大单净流入-净额"),
            "medium_net": row.get("中单净流入-净额"),
            "small_net": row.get("小单净流入-净额"),
        }

    def collect_one(self, code: str, session: Session, days: int = 10) -> int:
        market = stock_market(code)
        df = self._call_ak("stock_individual_fund_flow",
                           stock=code, market=market)
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.tail(days).iterrows():
            mapped = self._map_flow_row(code, row.to_dict())
            exists = session.query(StockMoneyFlow).filter_by(
                stock_code=code, trade_date=mapped["trade_date"]
            ).first()
            if exists:
                continue
            session.add(StockMoneyFlow(**mapped))
            count += 1

        session.commit()
        return count

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        total = 0
        for code, name in stock_list:
            try:
                n = self.collect_one(code, session)
                total += n
            except Exception as e:
                logger.error(f"[{code}] 资金流采集失败: {e}")
        logger.info(f"资金流采集完成, 共 {total} 条")
        return total
