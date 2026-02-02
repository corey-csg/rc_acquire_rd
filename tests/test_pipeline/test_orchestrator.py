from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from acquire.models.db import ChangeEvent, PipelineStatus
from acquire.pipeline.orchestrator import run_pipeline
from acquire.storage import repository


def _mock_session_factory(session):
    """Create a mock session factory that yields the test session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield session

    mock_factory = MagicMock()
    mock_factory.return_value = factory()
    # Each call needs a fresh context manager
    mock_factory.side_effect = lambda: factory()
    return mock_factory


def _triage_response(meaningful=True, links=None):
    return {
        "content": {
            "meaningful": meaningful,
            "triage_reasoning": "Test reasoning",
            "discovered_links": links or [],
        },
        "model": "deepseek/deepseek-v3.2",
        "prompt_tokens": 300,
        "completion_tokens": 80,
        "total_tokens": 380,
    }


def _classify_response(classification="RFP", confidence=0.95):
    return {
        "content": {
            "classification": classification,
            "confidence": confidence,
            "reasoning": "Test classification reasoning",
            "key_signals": ["signal1"],
        },
        "model": "deepseek/deepseek-v3.2",
        "prompt_tokens": 500,
        "completion_tokens": 100,
        "total_tokens": 600,
    }


def _enrich_response():
    return {
        "content": {
            "summary": "Test summary of procurement opportunity",
            "recommended_actions": ["Action 1", "Action 2"],
            "urgency": "HIGH",
            "key_dates": [],
            "relevant_agencies": [],
        },
        "model": "deepseek/deepseek-v3.2",
        "prompt_tokens": 800,
        "completion_tokens": 200,
        "total_tokens": 1000,
    }


@pytest.mark.asyncio
async def test_parent_event_full_pipeline(session):
    """Parent event flows through triage → classify → enrich → notify."""
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://www.usda.gov/reconnect",
        diff_text="+ New NOFO: ReConnect Round 5 now open for applications.",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    event_id = event.id

    mock_factory = _mock_session_factory(session)

    with (
        patch("acquire.pipeline.orchestrator.get_session_factory", return_value=mock_factory),
        patch("acquire.pipeline.triage.chat_completion", new_callable=AsyncMock, return_value=_triage_response()),
        patch("acquire.pipeline.triage.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.classifier.chat_completion", new_callable=AsyncMock, return_value=_classify_response()),
        patch("acquire.pipeline.classifier.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.enricher.chat_completion", new_callable=AsyncMock, return_value=_enrich_response()),
        patch("acquire.pipeline.enricher.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.orchestrator.notify_slack", new_callable=AsyncMock, return_value="ok") as mock_notify,
    ):
        await run_pipeline(event_id)

    # Refresh from DB
    updated = await repository.get_event(session, event_id)
    assert updated is not None
    assert updated.pipeline_status == PipelineStatus.NOTIFIED.value
    assert updated.classification == "RFP"
    assert updated.summary == "Test summary of procurement opportunity"
    assert updated.urgency == "HIGH"
    assert updated.slack_message_ts == "ok"


@pytest.mark.asyncio
async def test_non_meaningful_triage_still_processes_links(session):
    """Non-meaningful triage result still creates child events from discovered links."""
    event = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://example.gov",
        diff_text="+ Updated page with link to https://grants.gov/opportunity",
        pipeline_status=PipelineStatus.FETCHED.value,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    event_id = event.id

    triage_resp = _triage_response(
        meaningful=False,
        links=[{"url": "https://grants.gov/opportunity", "reason": "Linked opportunity"}],
    )

    mock_factory = _mock_session_factory(session)

    # The child pipeline will also need mocks. It will skip triage (is_child=True)
    # and go straight to classify.
    with (
        patch("acquire.pipeline.orchestrator.get_session_factory", return_value=mock_factory),
        patch("acquire.pipeline.triage.chat_completion", new_callable=AsyncMock, return_value=triage_resp),
        patch("acquire.pipeline.triage.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.orchestrator.fetch_page_text", new_callable=AsyncMock, return_value="Page content about a grant opportunity"),
        patch("acquire.pipeline.classifier.chat_completion", new_callable=AsyncMock, return_value=_classify_response()),
        patch("acquire.pipeline.classifier.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.enricher.chat_completion", new_callable=AsyncMock, return_value=_enrich_response()),
        patch("acquire.pipeline.enricher.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.orchestrator.notify_slack", new_callable=AsyncMock, return_value="ok"),
    ):
        await run_pipeline(event_id)

    # Parent should be filtered out
    parent = await repository.get_event(session, event_id)
    assert parent is not None
    assert parent.pipeline_status == PipelineStatus.FILTERED_OUT.value

    # A child event should have been created and processed
    from sqlmodel import select

    result = await session.execute(
        select(ChangeEvent).where(ChangeEvent.parent_event_id == event_id)
    )
    children = result.scalars().all()
    assert len(children) == 1
    child = children[0]
    assert child.watch_url == "https://grants.gov/opportunity"
    assert child.parent_event_id == event_id
    assert child.pipeline_status == PipelineStatus.NOTIFIED.value


@pytest.mark.asyncio
async def test_child_event_skips_triage(session):
    """Child events skip triage and go directly to classify."""
    # Create parent first
    parent = ChangeEvent(
        watch_uuid="test-uuid",
        watch_url="https://example.gov",
        pipeline_status=PipelineStatus.NOTIFIED.value,
    )
    session.add(parent)
    await session.commit()
    await session.refresh(parent)

    # Create child event (already FETCHED with snapshot_text)
    child = await repository.create_child_event(
        session,
        parent=parent,
        url="https://grants.gov/nofo",
        page_text="Full text of the NOFO grant opportunity.",
    )
    child_id = child.id

    mock_factory = _mock_session_factory(session)
    mock_triage = AsyncMock()  # Should NOT be called

    with (
        patch("acquire.pipeline.orchestrator.get_session_factory", return_value=mock_factory),
        patch("acquire.pipeline.triage.chat_completion", mock_triage),
        patch("acquire.pipeline.classifier.chat_completion", new_callable=AsyncMock, return_value=_classify_response()),
        patch("acquire.pipeline.classifier.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.enricher.chat_completion", new_callable=AsyncMock, return_value=_enrich_response()),
        patch("acquire.pipeline.enricher.check_budget", new_callable=AsyncMock, return_value=True),
        patch("acquire.pipeline.orchestrator.notify_slack", new_callable=AsyncMock, return_value="ok"),
    ):
        await run_pipeline(child_id)

    # Triage LLM should never have been called
    mock_triage.assert_not_called()

    updated = await repository.get_event(session, child_id)
    assert updated is not None
    assert updated.pipeline_status == PipelineStatus.NOTIFIED.value
    assert updated.classification == "RFP"
    assert updated.parent_event_id == parent.id
