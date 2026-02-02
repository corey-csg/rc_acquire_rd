from __future__ import annotations

import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from acquire.llm.client import chat_completion
from acquire.llm.cost import check_budget, record_usage
from acquire.llm.prompts import load_prompt
from acquire.models.db import ChangeEvent, PipelineStatus
from acquire.models.schemas import EnrichmentResult
from acquire.storage import repository

logger = structlog.get_logger()

MAX_DIFF_CHARS = 6000
MAX_SNAPSHOT_CHARS = 3000


async def enrich(session: AsyncSession, event: ChangeEvent) -> EnrichmentResult | None:
    """Enrich a classified event with actionable intelligence. Returns None if budget exceeded."""
    if not await check_budget(session):
        logger.warning("enrichment_skipped_budget", event_id=event.id)
        return None

    prompt = load_prompt(
        "enrich",
        watch_url=event.watch_url,
        classification=event.classification,
        confidence=event.classification_confidence,
        diff_text=(event.diff_text or "")[:MAX_DIFF_CHARS],
        snapshot_text=(event.snapshot_text or "")[:MAX_SNAPSHOT_CHARS],
    )

    result = await chat_completion(
        messages=[
            {"role": "system", "content": "You are a government procurement intelligence analyst. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    content = result["content"]
    if not isinstance(content, dict):
        raise ValueError(f"LLM did not return valid JSON: {str(content)[:200]}")

    enrichment = EnrichmentResult(**content)

    # Record cost
    await record_usage(
        session,
        model=result["model"],
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
        event_id=event.id,
    )

    # Update event
    event.summary = enrichment.summary
    event.recommended_actions = json.dumps(enrichment.recommended_actions)
    event.urgency = enrichment.urgency
    event.key_dates = json.dumps(enrichment.key_dates) if enrichment.key_dates else None
    event.relevant_agencies = json.dumps(enrichment.relevant_agencies) if enrichment.relevant_agencies else None
    event.enrichment_model = result["model"]
    event.enrichment_tokens_used = result["total_tokens"]
    event.pipeline_status = PipelineStatus.ENRICHED.value
    await repository.update_event(session, event)

    logger.info(
        "enriched",
        event_id=event.id,
        urgency=enrichment.urgency,
        actions_count=len(enrichment.recommended_actions),
    )

    return enrichment
