from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from acquire.storage.database import init_db
from acquire.utils.logging import setup_logging
from acquire.api.webhooks import router as webhooks_router
from acquire.api.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield


app = FastAPI(title="RC/RD Acquire", version="0.1.0", lifespan=lifespan)

app.include_router(webhooks_router)
app.include_router(health_router)
