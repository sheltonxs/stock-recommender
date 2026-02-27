"""A股智选 - 基本面分析器

评分体系 100 分 = 估值(30) + 盈利能力(30) + 成长性(20) + 财务健康(20)
"""

from datetime import date


class FundamentalAnalyzer:
    """基本面评分引擎"""

    def score(self, data: dict, industry_avg_pe: float = 30.0,
              report_date: date | None = None) -> dict:
        """
        对基本面数据进行评分。

        Args:
            data: 包含 pe_ttm, pb, roe, gross_margin, net_margin,
                  revenue_yoy, profit_yoy, debt_ratio, current_ratio,
                  operating_cashflow 等字段的字典。
            industry_avg_pe: 行业平均市盈率，用于估值对比。

        Returns:
            {"total", "valuation", "profitability", "growth",
             "health", "signals"}
        """
        signals: list[str] = []

        # ---------- 估值 (30 分) ----------
        val_score = 0

        pe = data.get("pe_ttm")
        if pe is not None and pe > 0 and industry_avg_pe > 0:
            if pe < industry_avg_pe * 0.5:
                val_score += 12
                signals.append(f"PE({pe:.1f})低于行业均值50% \u2705")
            elif pe < industry_avg_pe:
                val_score += 8
                signals.append(f"PE({pe:.1f})低于行业均值 \u2705")
            elif pe < industry_avg_pe * 2:
                val_score += 4

        pb = data.get("pb")
        if pb is not None and pb > 0:
            if pb < 1:
                val_score += 10
                signals.append(f"PB({pb:.1f})破净 \u2705")
            elif pb < 2:
                val_score += 7
            elif pb < 5:
                val_score += 3

        # PEG = PE / profit_yoy（仅当 profit_yoy > 0 时有意义）
        profit_yoy = data.get("profit_yoy")
        if pe is not None and pe > 0 and profit_yoy is not None and profit_yoy > 0:
            peg = pe / profit_yoy
            if peg < 0.5:
                val_score += 8
                signals.append(f"PEG({peg:.2f})极低 \u2705")
            elif peg < 1:
                val_score += 6
            elif peg < 1.5:
                val_score += 3

        val_score = min(val_score, 30)

        # ---------- 盈利能力 (30 分) ----------
        profit_score = 0

        roe = data.get("roe")
        if roe is not None:
            if roe >= 20:
                profit_score += 12
                signals.append(f"ROE({roe:.1f}%)优秀 \u2705")
            elif roe >= 15:
                profit_score += 9
                signals.append(f"ROE({roe:.1f}%)良好 \u2705")
            elif roe >= 10:
                profit_score += 5
            else:
                profit_score += 2

        gm = data.get("gross_margin")
        if gm is not None:
            if gm > 50:
                profit_score += 8
                signals.append(f"毛利率({gm:.1f}%)高 \u2705")
            elif gm > 30:
                profit_score += 5
            else:
                profit_score += 2

        nm = data.get("net_margin")
        if nm is not None:
            if nm > 20:
                profit_score += 7
            elif nm > 10:
                profit_score += 4
            else:
                profit_score += 1

        profit_score = min(profit_score, 30)

        # ---------- 成长性 (20 分) ----------
        growth_score = 0

        rev_yoy = data.get("revenue_yoy")
        if rev_yoy is not None:
            if rev_yoy > 30:
                growth_score += 8
                signals.append(f"营收增长({rev_yoy:.1f}%)高速 \u2705")
            elif rev_yoy > 20:
                growth_score += 6
            elif rev_yoy > 10:
                growth_score += 3
            else:
                growth_score += 1

        if profit_yoy is not None:
            if profit_yoy > 40:
                growth_score += 7
                signals.append(f"净利润增长({profit_yoy:.1f}%)爆发 \u2705")
            elif profit_yoy > 25:
                growth_score += 5
            elif profit_yoy > 10:
                growth_score += 3
            else:
                growth_score += 1

        growth_score = min(growth_score, 20)

        # ---------- 财务健康 (20 分) ----------
        health_score = 0

        dr = data.get("debt_ratio")
        if dr is not None:
            if dr < 40:
                health_score += 7
                signals.append(f"资产负债率({dr:.1f}%)低 \u2705")
            elif dr < 60:
                health_score += 5
            elif dr < 80:
                health_score += 2
            else:
                signals.append(f"\u26a0\ufe0f 资产负债率({dr:.1f}%)偏高")

        ocf = data.get("operating_cashflow")
        if ocf is not None:
            if ocf > 0:
                health_score += 7
                if ocf > 10:
                    signals.append("经营现金流充沛 \u2705")
            else:
                signals.append("\u26a0\ufe0f 经营现金流为负")

        cr = data.get("current_ratio")
        if cr is not None:
            if cr > 2:
                health_score += 6
            elif cr > 1.5:
                health_score += 4
            elif cr > 1:
                health_score += 2

        health_score = min(health_score, 20)

        total = val_score + profit_score + growth_score + health_score

        # ---------- 财报新鲜度惩罚（连续衰减曲线） ----------
        freshness_factor = 1.0
        if report_date is not None:
            months_old = (date.today() - report_date).days / 30.0
            if months_old > 18:
                freshness_factor = 0.2
                signals.append(f"\u26a0\ufe0f 财报已过期{months_old:.0f}个月(2折)")
            elif months_old > 12:
                freshness_factor = 0.5 - (months_old - 12) * 0.033  # 12个月=50%, 18个月≈30%
                signals.append(f"\u26a0\ufe0f 财报{months_old:.0f}个月前({freshness_factor:.0%})")
            elif months_old > 6:
                freshness_factor = 0.8 - (months_old - 6) * 0.05  # 6个月=80%, 12个月=50%
                signals.append(f"\u26a0\ufe0f 财报{months_old:.0f}个月前({freshness_factor:.0%})")
            total = round(total * freshness_factor)

        return {
            "total": min(total, 100),
            "valuation": val_score,
            "profitability": profit_score,
            "growth": growth_score,
            "health": health_score,
            "signals": signals,
        }
