"""A股智选 - 综合评分器

加权多因子评分：
  total = 技术面 * 0.30 + 基本面 * 0.25 + 资金面 * 0.25 + 情绪面 * 0.20
"""

import json

from app.config import Settings


class CompositeScorer:

    def __init__(self, settings: Settings | None = None):
        s = settings or Settings()
        self.w_tech = s.weight_technical
        self.w_fund = s.weight_fundamental
        self.w_money = s.weight_money_flow
        self.w_sent = s.weight_sentiment

    def compute(
        self,
        technical: dict,
        fundamental: dict,
        money_flow: dict,
        sentiment: dict,
    ) -> dict:
        tech_s = technical.get("total", 0)
        fund_s = fundamental.get("total", 0)
        money_s = money_flow.get("total", 0)
        sent_s = sentiment.get("total", 0)

        total = round(
            tech_s * self.w_tech
            + fund_s * self.w_fund
            + money_s * self.w_money
            + sent_s * self.w_sent,
            1,
        )

        # --- 信号冲突检测 ---
        conflict_signals = []
        dim_pairs = [
            ("技术面", tech_s, "资金面", money_s),
            ("技术面", tech_s, "基本面", fund_s),
            ("基本面", fund_s, "资金面", money_s),
        ]
        conflict_count = 0
        for name_a, score_a, name_b, score_b in dim_pairs:
            if abs(score_a - score_b) >= 40:
                conflict_count += 1
                conflict_signals.append(
                    f"\u26a0\ufe0f {name_a}({score_a:.0f})与{name_b}({score_b:.0f})信号冲突"
                )

        if conflict_count >= 2:
            total = round(total * 0.85, 1)
        elif conflict_count == 1:
            total = round(total * 0.93, 1)

        if total >= 80:
            risk, advice = "低", "强烈看多"
        elif total >= 70:
            risk, advice = "低", "偏多"
        elif total >= 55:
            risk, advice = "中", "中性偏多"
        elif total >= 40:
            risk, advice = "中", "中性"
        else:
            risk, advice = "高", "偏空"

        all_signals = (
            technical.get("signals", [])
            + fundamental.get("signals", [])
            + money_flow.get("signals", [])
            + sentiment.get("signals", [])
            + conflict_signals
        )
        bullish = [s for s in all_signals if "\u2705" in s]
        bearish = [s for s in all_signals if "\u26a0\ufe0f" in s]

        return {
            "total_score": total,
            "technical_score": tech_s,
            "fundamental_score": fund_s,
            "money_flow_score": money_s,
            "sentiment_score": sent_s,
            "risk_level": risk,
            "advice": advice,
            "signals_bullish": bullish,
            "signals_bearish": bearish,
            "signals_json": json.dumps(
                {"bullish": bullish, "bearish": bearish},
                ensure_ascii=False,
            ),
        }
