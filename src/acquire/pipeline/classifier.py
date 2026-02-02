from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from acquire.llm.client import chat_completion
from acquire.llm.cost import check_budget, record_usage
from acquire.llm.prompts import load_prompt
from acquire.models.db import ChangeEvent, PipelineStatus
from acquire.models.schemas import ClassificationResult
from acquire.storage import repository

logger = structlog.get_logger()

MAX_DIFF_CHARS = 6000


async def classify(session: AsyncSession, event: ChangeEvent) -> ClassificationResult | None:
    """Classify a change event using LLM. Returns None if budget exceeded."""
    if not await check_budget(session):
        logger.warning("classification_skipped_budget", event_id=event.id)
        return None

    diff_text = (event.diff_text or event.snapshot_text or "")[:MAX_DIFF_CHARS]

    prompt = load_prompt(
        "classify",
        watch_url=event.watch_url,
        diff_text=diff_text,
    )

    result = await chat_completion(
        messages=[
            {"role": "system", "content": "You are a government procurement intelligence analyst. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    content = result["content"]
    if not isinstance(content, dict):
        raise ValueError(f"LLM did not return valid JSON: {str(content)[:200]}")

    classification = ClassificationResult(**content)

    # Record cost
    await record_usage(
        session,
        model=result["model"],
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
        event_id=event.id,
    )

    # Update event
    event.classification = classification.classification
    event.classification_confidence = classification.confidence
    event.classification_reasoning = classification.reasoning
    event.classification_model = result["model"]
    event.classification_tokens_used = result["total_tokens"]
    event.pipeline_status = PipelineStatus.CLASSIFIED.value
    await repository.update_event(session, event)

    logger.info(
        "classified",
        event_id=event.id,
        classification=classification.classification,
        confidence=classification.confidence,
    )

    return classification
