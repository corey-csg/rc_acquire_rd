from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from acquire.models.db import ChangeEvent, CostLedger


async def create_event(session: AsyncSession, watch_uuid: str, watch_url: str) -> ChangeEvent:
    event = ChangeEvent(watch_uuid=watch_uuid, watch_url=watch_url)
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def update_event(session: AsyncSession, event: ChangeEvent) -> ChangeEvent:
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_event(session: AsyncSession, event_id: int) -> ChangeEvent | None:
    return await session.get(ChangeEvent, event_id)


async def get_events_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(ChangeEvent.id)))
    return result.scalar_one()


async def get_events_today_count(session: AsyncSession) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = await session.execute(
        select(func.count(ChangeEvent.id)).where(
            func.date(ChangeEvent.received_at) == today
        )
    )
    return result.scalar_one()


async def record_cost(
    session: AsyncSession,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    event_id: int | None = None,
) -> CostLedger:
    entry = CostLedger(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=cost_usd,
        event_id=event_id,
    )
    session.add(entry)
    await session.commit()
    return entry


async def get_daily_spend(session: AsyncSession, date: str | None = None) -> float:
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = await session.execute(
        select(func.coalesce(func.sum(CostLedger.estimated_cost_usd), 0.0)).where(
            CostLedger.date == date
        )
    )
    return result.scalar_one()
