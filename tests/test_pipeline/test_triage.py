from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from acquire.models.db import ChangeEvent, PipelineStatus
from acquire.pipeline.triage import triage


@pytest.mark.asyncio
async def test_triage_meaningful_with_links(session):
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://www.usda.gov/reconnect",
        diff_text="+ New NOFO: ReConnect Round 5 now open. See https://www.grants.gov/reconnect-round5 for details.",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    mock_response = {
        "content": {
            "meaningful": True,
            "triage_reasoning": "New NOFO announcement for ReConnect program",
            "discovered_links": [
                {"url": "https://www.grants.gov/reconnect-round5", "reason": "ReConnect Round 5 NOFO"}
            ],
        },
        "model": "deepseek/deepseek-v3.2",
        "prompt_tokens": 300,
        "completion_tokens": 80,
        "total_tokens": 380,
    }

    with patch("acquire.pipeline.triage.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        with patch("acquire.pipeline.triage.check_budget", new_callable=AsyncMock, return_value=True):
            result = await triage(session, event)

    assert result is not None
    assert result.meaningful is True
    assert len(result.discovered_links) == 1
    assert result.discovered_links[0].url == "https://www.grants.gov/reconnect-round5"

    # Verify event was updated
    assert event.pipeline_status == PipelineStatus.TRIAGED.value
    assert event.triage_tokens_used == 380
    assert event.triage_result is not None
    assert event.discovered_links is not None


@pytest.mark.asyncio
async def test_triage_not_meaningful(session):
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://example.gov",
        diff_text="- Last updated: Jan 1\n+ Last updated: Feb 1",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    mock_response = {
        "content": {
            "meaningful": False,
            "triage_reasoning": "Date-only update, no substantive content change",
            "discovered_links": [],
        },
        "model": "deepseek/deepseek-v3.2",
        "prompt_tokens": 200,
        "completion_tokens": 50,
        "total_tokens": 250,
    }

    with patch("acquire.pipeline.triage.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        with patch("acquire.pipeline.triage.check_budget", new_callable=AsyncMock, return_value=True):
            result = await triage(session, event)

    assert result is not None
    assert result.meaningful is False
    assert len(result.discovered_links) == 0


@pytest.mark.asyncio
async def test_triage_skips_on_budget_exceeded(session):
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://example.gov",
        diff_text="Some content",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    with patch("acquire.pipeline.triage.check_budget", new_callable=AsyncMock, return_value=False):
        result = await triage(session, event)

    assert result is None


@pytest.mark.asyncio
async def test_triage_enforces_max_links(session):
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://example.gov",
        diff_text="Lots of links",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    mock_response = {
        "content": {
            "meaningful": True,
            "triage_reasoning": "Multiple opportunities",
            "discovered_links": [
                {"url": f"https://example.gov/link{i}", "reason": f"Link {i}"}
                for i in range(5)
            ],
        },
        "model": "deepseek/deepseek-v3.2",
        "prompt_tokens": 300,
        "completion_tokens": 100,
        "total_tokens": 400,
    }

    with patch("acquire.pipeline.triage.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        with patch("acquire.pipeline.triage.check_budget", new_callable=AsyncMock, return_value=True):
            result = await triage(session, event)

    assert result is not None
    # Default max_links_per_event is 3
    assert len(result.discovered_links) == 3
