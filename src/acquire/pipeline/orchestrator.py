from __future__ import annotations

import structlog

from acquire.models.db import PipelineStatus
from acquire.pipeline.fetcher import fetch_diff
from acquire.pipeline.classifier import classify
from acquire.pipeline.enricher import enrich
from acquire.pipeline.filter import should_enrich, should_notify, is_diff_too_small
from acquire.pipeline.notifier import notify_slack
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

        try:
            # Stage 1: Fetch diff from changedetection.io (skip if already fetched)
            if event.pipeline_status == PipelineStatus.RECEIVED.value:
                logger.info("pipeline_fetch", event_id=event_id)
                diff_text, snapshot_text = await fetch_diff(event.watch_uuid)
                event.diff_text = diff_text
                event.snapshot_text = snapshot_text
                event.pipeline_status = PipelineStatus.FETCHED.value
                await repository.update_event(session, event)

            # Stage 2: Filter trivially small diffs
            if is_diff_too_small(event.diff_text):
                logger.info("pipeline_filtered_small_diff", event_id=event_id)
                event.pipeline_status = PipelineStatus.FILTERED_OUT.value
                event.error_message = "Diff too small"
                await repository.update_event(session, event)
                return

            # Stage 3: Classify via LLM
            logger.info("pipeline_classify", event_id=event_id)
            classification = await classify(session, event)
            if not classification:
                event.pipeline_status = PipelineStatus.ERROR.value
                event.error_message = "Classification failed or budget exceeded"
                await repository.update_event(session, event)
                return

            # Stage 4: Filter non-actionable
            if not should_enrich(classification.classification):
                logger.info(
                    "pipeline_filtered_classification",
                    event_id=event_id,
                    classification=classification.classification,
                )
                event.pipeline_status = PipelineStatus.FILTERED_OUT.value
                await repository.update_event(session, event)
                return

            # Stage 5: Enrich via LLM
            logger.info("pipeline_enrich", event_id=event_id)
            enrichment = await enrich(session, event)
            if not enrichment:
                event.pipeline_status = PipelineStatus.ERROR.value
                event.error_message = "Enrichment failed or budget exceeded"
                await repository.update_event(session, event)
                return

            # Stage 6: Notify via Slack
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

            logger.info("pipeline_complete", event_id=event_id, status=event.pipeline_status)

        except Exception as e:
            logger.exception("pipeline_error", event_id=event_id, error=str(e))
            event.pipeline_status = PipelineStatus.ERROR.value
            event.error_message = str(e)[:500]
            await repository.update_event(session, event)
