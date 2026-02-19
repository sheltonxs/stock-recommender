"""A股智选 - 资金面分析器

基于每日资金流向数据进行评分（100 分）。
"""


class MoneyFlowAnalyzer:
    """资金面评分引擎"""

    def score(self, rows: list[dict]) -> dict:
        """
        对最近几日的资金流向数据评分。

        Args:
            rows: 按时间升序排列的资金流向记录列表，每条包含
                  main_net_inflow (万元), main_net_ratio (%),
                  super_large_net (万元)。

        Returns:
            {"total", "signals"}
        """
        signals: list[str] = []
        total_score = 0

        if not rows:
            return {"total": 0, "signals": ["无资金流向数据"]}

        # 取最近 3 天（或不足 3 天时取全部）
        recent = rows[-3:] if len(rows) >= 3 else rows

        # ---------- 近 3 日主力净流入总额 ----------
        inflow_sum = sum(r.get("main_net_inflow", 0) or 0 for r in recent)
        if inflow_sum > 50000:
            total_score += 25
            signals.append(f"近3日主力净流入{inflow_sum:.0f}万(大幅) \u2705")
        elif inflow_sum > 10000:
            total_score += 15
            signals.append(f"近3日主力净流入{inflow_sum:.0f}万 \u2705")
        elif inflow_sum > 0:
            total_score += 8
            signals.append(f"近3日主力小幅净流入 \u2705")

        # ---------- 连续 3 日主力净流入为正 ----------
        if len(recent) >= 3:
            all_positive = all(
                (r.get("main_net_inflow", 0) or 0) > 0 for r in recent
            )
            if all_positive:
                total_score += 15
                signals.append("连续3日主力净流入 \u2705")

        # ---------- 超大单占比 ----------
        latest = recent[-1]
        super_large = latest.get("super_large_net", 0) or 0
        main_inflow = latest.get("main_net_inflow", 0) or 0
        if main_inflow > 0 and super_large > 0:
            sl_ratio = abs(super_large / main_inflow * 100) if main_inflow != 0 else 0
            if sl_ratio > 10:
                total_score += 15
                signals.append(f"超大单占比{sl_ratio:.1f}% \u2705")

        # ---------- 主力净比 ----------
        net_ratio = latest.get("main_net_ratio", 0) or 0
        if net_ratio > 10:
            total_score += 20
            signals.append(f"主力净比{net_ratio:.1f}%(强势) \u2705")
        elif net_ratio > 5:
            total_score += 12
            signals.append(f"主力净比{net_ratio:.1f}% \u2705")
        elif net_ratio > 0:
            total_score += 5
        else:
            signals.append(f"\u26a0\ufe0f 主力净比{net_ratio:.1f}%(流出)")

        total_score = min(total_score, 100)
        return {"total": total_score, "signals": signals}
