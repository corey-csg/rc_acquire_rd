from __future__ import annotations

from acquire.llm.cost import estimate_cost


def test_estimate_cost_claude():
    cost = estimate_cost("anthropic/claude-sonnet-4", 1000, 500)
    # (1000 * 3.0 + 500 * 15.0) / 1_000_000 = (3000 + 7500) / 1_000_000 = 0.0105
    assert cost == 0.0105


def test_estimate_cost_unknown_model():
    cost = estimate_cost("unknown/model", 1000, 500)
    # Falls back to default rates (3.0, 15.0)
    assert cost == 0.0105
