from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from acquire.config import get_settings
from acquire.models.schemas import WebhookPayload
from acquire.storage.database import get_session
from acquire.storage import repository
from acquire.pipeline.orchestrator import run_pipeline

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks")


@router.post("/change")
async def receive_change(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    x_webhook_secret: str | None = Header(None),
):
    settings = get_settings()

    # Verify webhook secret if configured
    if settings.webhook_secret:
        if x_webhook_secret != settings.webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    event = await repository.create_event(
        session,
        watch_uuid=payload.watch_uuid,
        watch_url=payload.watch_url,
    )

    logger.info(
        "webhook_received",
        event_id=event.id,
        watch_uuid=payload.watch_uuid,
        watch_url=payload.watch_url,
    )

    background_tasks.add_task(run_pipeline, event.id)

    return {"status": "accepted", "event_id": event.id}
