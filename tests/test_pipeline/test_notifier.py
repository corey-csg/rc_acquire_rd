from __future__ import annotations

from acquire.models.db import ChangeEvent
from acquire.pipeline.notifier import _build_slack_blocks


def test_build_slack_blocks():
    event = ChangeEvent(
        id=42,
        watch_uuid="test",
        watch_url="https://www.usda.gov/reconnect",
        classification="RFP",
        classification_confidence=0.95,
        classification_model="anthropic/claude-sonnet-4",
        summary="USDA announces $1.1B ReConnect Round 5 NOFO",
        recommended_actions='["Register for industry day", "Prepare application"]',
        urgency="HIGH",
    )

    blocks = _build_slack_blocks(event)
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "header"
    assert "RFP" in blocks[0]["text"]["text"]
