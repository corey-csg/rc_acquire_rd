#!/usr/bin/env python3
"""Re-run the pipeline on a stored event (useful after prompt tuning)."""

import argparse
import asyncio

from acquire.storage.database import init_db, get_session_factory
from acquire.storage import repository
from acquire.pipeline.orchestrator import run_pipeline
from acquire.utils.logging import setup_logging


async def main(event_id: int, from_stage: str):
    setup_logging()
    await init_db()

    factory = get_session_factory()
    async with factory() as session:
        event = await repository.get_event(session, event_id)
        if not event:
            print(f"Event {event_id} not found")
            return

        print(f"Replaying event {event_id}: {event.watch_url}")
        print(f"Current status: {event.pipeline_status}")

        if from_stage == "classify":
            event.classification = None
            event.classification_confidence = None
            event.classification_reasoning = None
            event.summary = None
            event.recommended_actions = None
            event.urgency = None
            event.pipeline_status = "fetched"
            await repository.update_event(session, event)
        elif from_stage == "enrich":
            event.summary = None
            event.recommended_actions = None
            event.urgency = None
            event.pipeline_status = "classified"
            await repository.update_event(session, event)

    await run_pipeline(event_id)
    print("Replay complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay pipeline on a stored event")
    parser.add_argument("event_id", type=int)
    parser.add_argument("--from-stage", choices=["fetch", "classify", "enrich"], default="classify")
    args = parser.parse_args()
    asyncio.run(main(args.event_id, args.from_stage))
