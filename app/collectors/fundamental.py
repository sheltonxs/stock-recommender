"""财务数据采集"""

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.models.database import StockFundamental

logger = logging.getLogger(__name__)


class FundamentalCollector(BaseCollector):

    @staticmethod
    def _float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _map_financial_row(self, code: str, row: dict) -> dict:
        report_str = str(row.get("日期", ""))
        try:
            report_date = datetime.strptime(report_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            report_date = date.today()

        _f = self._float
        revenue_yoy = _f(row.get("营业总收入同比增长率(%)")) or _f(row.get("营业收入同比增长率(%)"))
        profit_yoy = _f(row.get("净利润同比增长率(%)")) or _f(row.get("归属净利润同比增长率(%)"))

        return {
            "stock_code": code,
            "report_date": report_date,
            "roe": _f(row.get("加权净资产收益率(%)")) or _f(row.get("净资产收益率(%)")),
            "gross_margin": _f(row.get("主营业务利润率(%)")),
            "net_margin": _f(row.get("销售净利率(%)")),
            "debt_ratio": _f(row.get("资产负债率(%)")),
            "current_ratio": _f(row.get("流动比率")),
            "revenue_yoy": revenue_yoy,
            "profit_yoy": profit_yoy,
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

        if not latest:
            latest = StockFundamental(stock_code=code, report_date=date.today())
            session.add(latest)

        pe_val = self._float(spot_row.get("市盈率-动态"))
        pb_val = self._float(spot_row.get("市净率"))
        mcap = self._float(spot_row.get("总市值"))
        fcap = self._float(spot_row.get("流通市值"))

        if pe_val is not None:
            latest.pe_ttm = pe_val
        if pb_val is not None:
            latest.pb = pb_val
        if mcap is not None:
            latest.market_cap = mcap / 1e8
        if fcap is not None:
            latest.float_market_cap = fcap / 1e8
        session.commit()

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        return self._collect_batch(
            stock_list, session,
            lambda code, name, sess: self.collect_one(code, sess),
            label="财务",
        )

    def enrich_pe_pb(self, stock_list: list[tuple[str, str]], session: Session):
        """批量补全缺失的 PE_TTM 和 PB（从 EPS/BVPS + 收盘价计算）"""
        from app.models.database import StockDaily
        enriched = 0
        skipped = 0
        consecutive_fails = 0
        for code, name in stock_list:
            try:
                latest = session.query(StockFundamental).filter_by(
                    stock_code=code
                ).order_by(StockFundamental.report_date.desc()).first()
                if not latest:
                    continue
                if latest.pe_ttm is not None and latest.pb is not None:
                    skipped += 1
                    continue

                # 获取最新收盘价
                latest_daily = session.query(StockDaily).filter_by(
                    stock_code=code
                ).order_by(StockDaily.trade_date.desc()).first()
                if not latest_daily or not latest_daily.close:
                    continue
                close = float(latest_daily.close)

                # 获取财务指标数据（EPS、每股净资产）
                df = self._call_ak("stock_financial_analysis_indicator",
                                   symbol=code, start_year="2024")
                if df is None or df.empty:
                    consecutive_fails += 1
                    if consecutive_fails >= self.CIRCUIT_BREAK_THRESHOLD:
                        logger.error(f"PE/PB补全连续{consecutive_fails}次失败，触发熔断")
                        break
                    continue

                consecutive_fails = 0
                row = df.iloc[0].to_dict()
                changed = False

                # PE_TTM = 收盘价 / 每股收益
                if latest.pe_ttm is None:
                    for key in ("摊薄每股收益(元)", "加权每股收益(元)", "每股收益_调整后(元)"):
                        eps = row.get(key)
                        if eps is not None:
                            try:
                                eps_val = float(eps)
                                if eps_val > 0:
                                    latest.pe_ttm = round(close / eps_val, 2)
                                    changed = True
                                    break
                            except (ValueError, TypeError):
                                pass

                # PB = 收盘价 / 每股净资产
                if latest.pb is None:
                    for key in ("每股净资产_调整后(元)", "每股净资产_调整前(元)"):
                        bvps = row.get(key)
                        if bvps is not None:
                            try:
                                bvps_val = float(bvps)
                                if bvps_val > 0:
                                    latest.pb = round(close / bvps_val, 2)
                                    changed = True
                                    break
                            except (ValueError, TypeError):
                                pass

                if changed:
                    session.commit()
                    enriched += 1
            except Exception as e:
                consecutive_fails += 1
                logger.debug(f"[{code}] PE/PB补全失败: {e}")
                if consecutive_fails >= self.CIRCUIT_BREAK_THRESHOLD:
                    logger.error(f"PE/PB补全连续{consecutive_fails}次失败，触发熔断")
                    break
        logger.info(f"PE/PB补全完成: 补全{enriched}只, 跳过{skipped}只(已有数据)")
