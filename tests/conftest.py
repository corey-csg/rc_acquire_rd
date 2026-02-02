from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

# Override settings before importing app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["CDIO_BASE_URL"] = "http://test-cdio:5000"
os.environ["CDIO_API_KEY"] = "test-key"
os.environ["OPENROUTER_API_KEY"] = "test-key"
os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"
os.environ["WEBHOOK_SECRET"] = ""

from acquire.main import app
from acquire.storage.database import get_session
from acquire.config import get_settings


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
