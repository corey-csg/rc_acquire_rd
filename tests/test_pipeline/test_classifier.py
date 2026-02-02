from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock

import pytest

from acquire.models.db import ChangeEvent, PipelineStatus
from acquire.pipeline.classifier import classify


@pytest.mark.asyncio
async def test_classify_rfp(session):
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://www.usda.gov/reconnect",
        diff_text="NOTICE OF FUNDING OPPORTUNITY - ReConnect Program Round 5 - Application Deadline March 15, 2026",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    mock_response = {
        "content": {
            "classification": "RFP",
            "confidence": 0.95,
            "reasoning": "NOFO with specific deadline",
            "key_signals": ["NOFO", "deadline", "ReConnect"],
        },
        "model": "anthropic/claude-sonnet-4",
        "prompt_tokens": 500,
        "completion_tokens": 100,
        "total_tokens": 600,
    }

    with patch("acquire.pipeline.classifier.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        with patch("acquire.pipeline.classifier.check_budget", new_callable=AsyncMock, return_value=True):
            result = await classify(session, event)

    assert result is not None
    assert result.classification == "RFP"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_skips_on_budget_exceeded(session):
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://example.gov",
        diff_text="Some diff content that is long enough to process",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    with patch("acquire.pipeline.classifier.check_budget", new_callable=AsyncMock, return_value=False):
        result = await classify(session, event)

    assert result is None
