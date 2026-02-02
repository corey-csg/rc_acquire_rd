from __future__ import annotations

import os
from unittest.mock import patch, AsyncMock

import pytest

from acquire.config import Settings


@pytest.mark.asyncio
async def test_webhook_creates_event(client):
    with patch("acquire.api.webhooks.run_pipeline", new_callable=AsyncMock):
        resp = await client.post("/webhooks/change", json={
            "watch_uuid": "abc-123",
            "watch_url": "https://example.gov/page",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert "event_id" in data


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(client):
    secret_settings = Settings(webhook_secret="real-secret")
    with patch("acquire.api.webhooks.get_settings", return_value=secret_settings):
        resp = await client.post(
            "/webhooks/change",
            json={"watch_uuid": "abc-123", "watch_url": "https://example.gov"},
            headers={"x-webhook-secret": "wrong-secret"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "events_total" in data
