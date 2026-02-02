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
    # Verify plain dash (not em dash) for Slack compatibility
    assert " - " in blocks[0]["text"]["text"]


def test_build_slack_blocks_child_event():
    """Child event includes 'Discovered via Event #N' in context block."""
    event = ChangeEvent(
        id=43,
        watch_uuid="test",
        watch_url="https://grants.gov/reconnect-round5",
        classification="RFP",
        classification_confidence=0.97,
        classification_model="deepseek/deepseek-v3.2",
        summary="Official NOFO for ReConnect Round 5",
        recommended_actions='["Download full NOFO", "Identify eligible areas"]',
        urgency="CRITICAL",
        parent_event_id=42,
    )

    blocks = _build_slack_blocks(event)

    # Find the context block
    context_block = next(b for b in blocks if b["type"] == "context")
    context_texts = [el["text"] for el in context_block["elements"]]

    assert any("Discovered via Event #42" in t for t in context_texts)
    assert any("Event #43" in t for t in context_texts)
    assert any("Confidence: 97%" in t for t in context_texts)
