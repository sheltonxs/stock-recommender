"""财务数据采集"""

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.models.database import StockFundamental

logger = logging.getLogger(__name__)


class FundamentalCollector(BaseCollector):

    def _map_financial_row(self, code: str, row: dict) -> dict:
        report_str = str(row.get("日期", ""))
        try:
            report_date = datetime.strptime(report_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            report_date = date.today()

        return {
            "stock_code": code,
            "report_date": report_date,
            "roe": row.get("净资产收益率(%)"),
            "gross_margin": row.get("主营业务利润率(%)"),
            "net_margin": row.get("销售净利率(%)"),
            "debt_ratio": row.get("资产负债率(%)"),
            "current_ratio": row.get("流动比率"),
        }

    def collect_one(self, code: str, session: Session) -> int:
        df = self._call_ak("stock_financial_analysis_indicator",
                           symbol=code, start_year="2023")
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.head(4).iterrows():
            mapped = self._map_financial_row(code, row.to_dict())
            exists = session.query(StockFundamental).filter_by(
                stock_code=code, report_date=mapped["report_date"]
            ).first()
            if exists:
                continue
            session.add(StockFundamental(**mapped))
            count += 1

        session.commit()
        return count

    def enrich_from_spot(self, code: str, spot_row: dict, session: Session):
        latest = session.query(StockFundamental).filter_by(
            stock_code=code
        ).order_by(StockFundamental.report_date.desc()).first()

        if latest:
            latest.pe_ttm = spot_row.get("市盈率-动态")
            latest.pb = spot_row.get("市净率")
            latest.market_cap = (spot_row.get("总市值") or 0) / 1e8
            latest.float_market_cap = (spot_row.get("流通市值") or 0) / 1e8
            session.commit()

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        total = 0
        for code, name in stock_list:
            try:
                n = self.collect_one(code, session)
                total += n
            except Exception as e:
                logger.error(f"[{code}] 财务采集失败: {e}")
        logger.info(f"财务采集完成, 共 {total} 条")
        return total
