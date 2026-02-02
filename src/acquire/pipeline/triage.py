from __future__ import annotations

import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from acquire.config import get_settings
from acquire.llm.client import chat_completion
from acquire.llm.cost import check_budget, record_usage
from acquire.llm.prompts import load_prompt
from acquire.models.db import ChangeEvent, PipelineStatus
from acquire.models.schemas import TriageResult
from acquire.storage import repository

logger = structlog.get_logger()

MAX_DIFF_CHARS = 4000


async def triage(session: AsyncSession, event: ChangeEvent) -> TriageResult | None:
    """Quick LLM triage: is this change meaningful? Any links to discover?

    Returns None if budget exceeded or triage fails.
    """
    if not await check_budget(session):
        logger.warning("triage_skipped_budget", event_id=event.id)
        return None

    yaml_config = get_settings().load_yaml_config()
    llm_config = yaml_config.get("llm", {})
    link_config = yaml_config.get("link_discovery", {})
    max_links = link_config.get("max_links_per_event", 3)

    diff_text = (event.diff_text or event.snapshot_text or "")[:MAX_DIFF_CHARS]

    prompt = load_prompt(
        "triage",
        watch_url=event.watch_url,
        diff_text=diff_text,
        max_links=max_links,
    )

    result = await chat_completion(
        messages=[
            {"role": "system", "content": "You are a government procurement intelligence analyst. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        model=llm_config.get("triage_model"),
        max_tokens=llm_config.get("max_tokens_triage", 512),
        temperature=llm_config.get("temperature", 0.1),
        response_format={"type": "json_object"},
    )

    content = result["content"]
    if not isinstance(content, dict):
        raise ValueError(f"Triage LLM did not return valid JSON: {str(content)[:200]}")

    triage_result = TriageResult(**content)

    # Enforce max links limit
    triage_result.discovered_links = triage_result.discovered_links[:max_links]

    # Record cost
    await record_usage(
        session,
        model=result["model"],
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
        event_id=event.id,
    )

    # Update event with triage data
    event.triage_result = json.dumps({
        "meaningful": triage_result.meaningful,
        "triage_reasoning": triage_result.triage_reasoning,
    })
    event.triage_tokens_used = result["total_tokens"]
    event.discovered_links = json.dumps(
        [{"url": l.url, "reason": l.reason} for l in triage_result.discovered_links]
    ) if triage_result.discovered_links else None
    event.pipeline_status = PipelineStatus.TRIAGED.value
    await repository.update_event(session, event)

    logger.info(
        "triaged",
        event_id=event.id,
        meaningful=triage_result.meaningful,
        links_found=len(triage_result.discovered_links),
    )

    return triage_result
