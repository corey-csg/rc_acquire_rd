from __future__ import annotations

import json

import structlog

from acquire.config import get_settings
from acquire.models.db import PipelineStatus
from acquire.pipeline.fetcher import fetch_diff
from acquire.pipeline.triage import triage
from acquire.pipeline.classifier import classify
from acquire.pipeline.enricher import enrich
from acquire.pipeline.filter import should_enrich, should_notify, is_diff_too_small
from acquire.pipeline.notifier import notify_slack
from acquire.pipeline.crawler import fetch_page_text
from acquire.storage.database import get_session_factory
from acquire.storage import repository

logger = structlog.get_logger()


async def run_pipeline(event_id: int):
    """Run the full pipeline for a change event. Called as a background task."""
    factory = get_session_factory()

    async with factory() as session:
        event = await repository.get_event(session, event_id)
        if not event:
            logger.error("event_not_found", event_id=event_id)
            return

        is_child = event.parent_event_id is not None

        try:
            # Stage 1: Fetch diff from changedetection.io (skip if already fetched or child)
            if event.pipeline_status == PipelineStatus.RECEIVED.value:
                logger.info("pipeline_fetch", event_id=event_id)
                diff_text, snapshot_text = await fetch_diff(event.watch_uuid)
                event.diff_text = diff_text
                event.snapshot_text = snapshot_text
                event.pipeline_status = PipelineStatus.FETCHED.value
                await repository.update_event(session, event)

            # Stage 2: Filter trivially small diffs
            if is_diff_too_small(event.diff_text) and not event.snapshot_text:
                logger.info("pipeline_filtered_small_diff", event_id=event_id)
                event.pipeline_status = PipelineStatus.FILTERED_OUT.value
                event.error_message = "Diff too small"
                await repository.update_event(session, event)
                return

            # Stage 3: Triage (skip for child events — they already passed discovery)
            triage_result = None
            if not is_child:
                logger.info("pipeline_triage", event_id=event_id)
                triage_result = await triage(session, event)
                if not triage_result:
                    event.pipeline_status = PipelineStatus.ERROR.value
                    event.error_message = "Triage failed or budget exceeded"
                    await repository.update_event(session, event)
                    return

                if not triage_result.meaningful:
                    logger.info(
                        "pipeline_filtered_triage",
                        event_id=event_id,
                        reasoning=triage_result.triage_reasoning,
                    )
                    event.pipeline_status = PipelineStatus.FILTERED_OUT.value
                    event.error_message = f"Triage: {triage_result.triage_reasoning}"
                    await repository.update_event(session, event)
                    # Still process discovered links even if parent is not meaningful
                    await _process_discovered_links(session, event, triage_result)
                    return

            # Stage 4: Classify via LLM
            logger.info("pipeline_classify", event_id=event_id)
            classification = await classify(session, event)
            if not classification:
                event.pipeline_status = PipelineStatus.ERROR.value
                event.error_message = "Classification failed or budget exceeded"
                await repository.update_event(session, event)
                return

            # Stage 5: Filter non-actionable
            if not should_enrich(classification.classification):
                logger.info(
                    "pipeline_filtered_classification",
                    event_id=event_id,
                    classification=classification.classification,
                )
                event.pipeline_status = PipelineStatus.FILTERED_OUT.value
                await repository.update_event(session, event)
                return

            # Stage 6: Enrich via LLM
            logger.info("pipeline_enrich", event_id=event_id)
            enrichment = await enrich(session, event)
            if not enrichment:
                event.pipeline_status = PipelineStatus.ERROR.value
                event.error_message = "Enrichment failed or budget exceeded"
                await repository.update_event(session, event)
                return

            # Stage 7: Notify via Slack
            if should_notify(classification.classification):
                logger.info("pipeline_notify", event_id=event_id)
                result = await notify_slack(event)
                if result:
                    event.slack_message_ts = result
                    event.pipeline_status = PipelineStatus.NOTIFIED.value
                else:
                    event.pipeline_status = PipelineStatus.ERROR.value
                    event.error_message = "Slack notification failed"
                await repository.update_event(session, event)
            else:
                event.pipeline_status = PipelineStatus.ENRICHED.value
                await repository.update_event(session, event)

            # Stage 8: Process discovered links (parent events only)
            if triage_result and not is_child:
                await _process_discovered_links(session, event, triage_result)

            logger.info("pipeline_complete", event_id=event_id, status=event.pipeline_status)

        except Exception as e:
            logger.exception("pipeline_error", event_id=event_id, error=str(e))
            event.pipeline_status = PipelineStatus.ERROR.value
            event.error_message = str(e)[:500]
            await repository.update_event(session, event)


async def _process_discovered_links(session, parent_event, triage_result):
    """Fetch each discovered link, create a child event, and run the pipeline on it."""
    yaml_config = get_settings().load_yaml_config()
    link_config = yaml_config.get("link_discovery", {})

    if not link_config.get("enabled", True):
        return

    if not triage_result.discovered_links:
        return

    max_chars = link_config.get("max_page_fetch_chars", 8000)

    for link in triage_result.discovered_links:
        try:
            logger.info(
                "link_discovery_fetch",
                parent_event_id=parent_event.id,
                url=link.url,
                reason=link.reason,
            )

            page_text = await fetch_page_text(link.url, max_chars=max_chars)
            if not page_text:
                logger.info("link_discovery_empty", url=link.url)
                continue

            child = await repository.create_child_event(
                session,
                parent=parent_event,
                url=link.url,
                page_text=page_text,
            )

            logger.info(
                "link_discovery_child_created",
                parent_event_id=parent_event.id,
                child_event_id=child.id,
                url=link.url,
            )

            # Run pipeline on child (will skip triage since is_child=True)
            await run_pipeline(child.id)

        except Exception as e:
            logger.warning(
                "link_discovery_error",
                parent_event_id=parent_event.id,
                url=link.url,
                error=str(e)[:200],
            )
