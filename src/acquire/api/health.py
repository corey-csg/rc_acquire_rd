from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from acquire.models.schemas import HealthResponse
from acquire.storage.database import get_session
from acquire.storage import repository

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)):
    total = await repository.get_events_count(session)
    today = await repository.get_events_today_count(session)
    return HealthResponse(events_total=total, events_today=today)
