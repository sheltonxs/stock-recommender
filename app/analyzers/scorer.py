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

    # 数据缺失检测阈值: 低于此值视为"无有效数据"
    _NO_DATA_THRESHOLD = 5

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

        # --- 缺失维度处理: 权重重分配 ---
        # 当维度数据缺失(分数极低且无信号)时，将其权重按比例分配给有数据的维度
        dims = [
            ("tech", tech_s, self.w_tech, technical.get("signals", [])),
            ("fund", fund_s, self.w_fund, fundamental.get("signals", [])),
            ("money", money_s, self.w_money, money_flow.get("signals", [])),
            ("sent", sent_s, self.w_sent, sentiment.get("signals", [])),
        ]
        has_data = {}
        for name, score, weight, signals in dims:
            # 有信号 或 分数>阈值 → 视为有有效数据
            has_data[name] = bool(signals) or score > self._NO_DATA_THRESHOLD

        active_weight = sum(w for n, s, w, _ in dims if has_data[n])
        if active_weight <= 0:
            active_weight = 1.0  # fallback

        total = 0.0
        for name, score, weight, signals in dims:
            if has_data[name]:
                # 有数据的维度按比例获得更多权重
                adjusted_weight = weight / active_weight
                total += score * adjusted_weight
            # 无数据的维度不参与计算（权重自动被有数据维度吸收）

        total = round(total, 1)

        # --- 信号冲突检测: 只对有数据的维度进行 ---
        conflict_signals = []
        scored_dims = [(n, s) for n, s, _, _ in dims if has_data[n]]
        conflict_count = 0
        for i in range(len(scored_dims)):
            for j in range(i + 1, len(scored_dims)):
                name_a, score_a = scored_dims[i]
                name_b, score_b = scored_dims[j]
                _DIM_LABELS = {"tech": "技术面", "fund": "基本面", "money": "资金面", "sent": "情绪面"}
                if abs(score_a - score_b) >= 40:
                    conflict_count += 1
                    conflict_signals.append(
                        f"\u26a0\ufe0f {_DIM_LABELS[name_a]}({score_a:.0f})与{_DIM_LABELS[name_b]}({score_b:.0f})信号冲突"
                    )

        if conflict_count >= 2:
            total = round(total * 0.85, 1)
        elif conflict_count == 1:
            total = round(total * 0.93, 1)

        total = max(0.0, min(100.0, total))

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
