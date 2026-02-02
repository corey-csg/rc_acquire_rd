from __future__ import annotations

import json

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
        key_dates='["2026-03-15: Application deadline", "2026-02-20: Industry day"]',
        relevant_agencies='["USDA", "Rural Utilities Service"]',
        enrichment_model="deepseek/deepseek-v3.2",
    )

    blocks = _build_slack_blocks(event)

    # Header
    assert blocks[0]["type"] == "header"
    assert "RFP" in blocks[0]["text"]["text"]
    assert " - " in blocks[0]["text"]["text"]

    # Divider after header
    assert blocks[1]["type"] == "divider"

    # Source with :link: emoji
    source_block = blocks[2]
    assert source_block["type"] == "section"
    assert ":link:" in source_block["text"]["text"]

    # Find next steps (numbered actions)
    next_steps = next(b for b in blocks if b["type"] == "section" and ":clipboard:" in b["text"]["text"])
    assert "1. Register for industry day" in next_steps["text"]["text"]
    assert "2. Prepare application" in next_steps["text"]["text"]

    # Key dates section
    dates_block = next(b for b in blocks if b["type"] == "section" and ":calendar:" in b["text"]["text"])
    assert "2026-03-15: Application deadline" in dates_block["text"]["text"]

    # Agencies section
    agencies_block = next(b for b in blocks if b["type"] == "section" and ":office:" in b["text"]["text"])
    assert "USDA" in agencies_block["text"]["text"]
    assert "Rural Utilities Service" in agencies_block["text"]["text"]

    # Context block: single element with pipe-separated parts
    context_block = next(b for b in blocks if b["type"] == "context")
    context_text = context_block["elements"][0]["text"]
    assert "Confidence: 95%" in context_text
    assert "deepseek/deepseek-v3.2" in context_text
    assert "Event #42" in context_text

    # Dividers: at least 3 (after header, after summary, before footer)
    divider_count = sum(1 for b in blocks if b["type"] == "divider")
    assert divider_count >= 3


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
        enrichment_model="deepseek/deepseek-v3.2",
    )

    blocks = _build_slack_blocks(event)

    # Context block is a single element with pipe separators
    context_block = next(b for b in blocks if b["type"] == "context")
    context_text = context_block["elements"][0]["text"]

    assert "Discovered via Event #42" in context_text
    assert "Event #43" in context_text
    assert "Confidence: 97%" in context_text


def test_build_slack_blocks_minimal():
    """Event with no optional enrichment fields still renders cleanly."""
    event = ChangeEvent(
        id=1,
        watch_uuid="test",
        watch_url="https://example.gov",
        classification="INFORMATIONAL",
        urgency="LOW",
    )

    blocks = _build_slack_blocks(event)

    assert blocks[0]["type"] == "header"
    # Should not crash, and should have context at the end
    context_block = next(b for b in blocks if b["type"] == "context")
    assert "Event #1" in context_block["elements"][0]["text"]
