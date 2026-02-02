from __future__ import annotations

from pydantic import BaseModel


class WebhookPayload(BaseModel):
    watch_uuid: str
    watch_url: str = ""


class ClassificationResult(BaseModel):
    classification: str
    confidence: float
    reasoning: str
    key_signals: list[str] = []


class EnrichmentResult(BaseModel):
    summary: str
    recommended_actions: list[str]
    urgency: str
    key_dates: list[str] = []
    relevant_agencies: list[str] = []


class DiscoveredLink(BaseModel):
    url: str
    reason: str


class TriageResult(BaseModel):
    meaningful: bool
    triage_reasoning: str
    discovered_links: list[DiscoveredLink] = []


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    events_total: int = 0
    events_today: int = 0
