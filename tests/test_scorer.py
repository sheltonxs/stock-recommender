"""Tests for the CompositeScorer."""

from app.analyzers.scorer import CompositeScorer
from app.config import Settings


def test_composite_score():
    s = Settings()
    scorer = CompositeScorer(s)
    result = scorer.compute(
        technical={"total": 80, "signals": ["均线多头 \u2705"]},
        fundamental={"total": 90, "signals": ["ROE高 \u2705"]},
        money_flow={"total": 70, "signals": ["主力净流入"]},
        sentiment={"total": 60, "signals": ["板块热度前5"]},
    )
    expected = 80 * 0.3 + 90 * 0.25 + 70 * 0.25 + 60 * 0.2
    assert abs(result["total_score"] - expected) < 0.1
    assert result["risk_level"] in ("低", "中", "高")
    assert len(result["signals_bullish"]) > 0


def test_risk_levels():
    scorer = CompositeScorer()
    high = scorer.compute(
        technical={"total": 90, "signals": []},
        fundamental={"total": 90, "signals": []},
        money_flow={"total": 90, "signals": []},
        sentiment={"total": 90, "signals": []},
    )
    assert high["risk_level"] == "低"

    low = scorer.compute(
        technical={"total": 20, "signals": []},
        fundamental={"total": 20, "signals": []},
        money_flow={"total": 20, "signals": []},
        sentiment={"total": 20, "signals": []},
    )
    assert low["risk_level"] == "高"
