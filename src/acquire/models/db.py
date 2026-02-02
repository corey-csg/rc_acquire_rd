from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from sqlmodel import SQLModel, Field


class PipelineStatus(str, Enum):
    RECEIVED = "received"
    FETCHED = "fetched"
    TRIAGED = "triaged"
    CLASSIFIED = "classified"
    ENRICHED = "enriched"
    NOTIFIED = "notified"
    FILTERED_OUT = "filtered_out"
    ERROR = "error"


class Classification(str, Enum):
    RFI = "RFI"
    RFP = "RFP"
    ACTIONABLE = "ACTIONABLE"
    INFORMATIONAL = "INFORMATIONAL"
    IRRELEVANT = "IRRELEVANT"


class Urgency(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ChangeEvent(SQLModel, table=True):
    __tablename__ = "change_events"

    id: Optional[int] = Field(default=None, primary_key=True)

    # From webhook
    watch_uuid: str = Field(index=True)
    watch_url: str = ""
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # From changedetection.io fetch
    diff_text: Optional[str] = None
    snapshot_text: Optional[str] = None

    # Classification
    classification: Optional[str] = None
    classification_confidence: Optional[float] = None
    classification_reasoning: Optional[str] = None
    classification_model: Optional[str] = None
    classification_tokens_used: Optional[int] = None

    # Enrichment
    summary: Optional[str] = None
    recommended_actions: Optional[str] = None  # JSON list stored as string
    urgency: Optional[str] = None
    key_dates: Optional[str] = None  # JSON list stored as string
    relevant_agencies: Optional[str] = None  # JSON list stored as string
    enrichment_model: Optional[str] = None
    enrichment_tokens_used: Optional[int] = None

    # Triage
    triage_result: Optional[str] = None  # JSON: {"meaningful": bool, "triage_reasoning": "..."}
    triage_tokens_used: Optional[int] = None
    discovered_links: Optional[str] = None  # JSON: [{"url": "...", "reason": "..."}]

    # Parent-child linkage for discovered links
    parent_event_id: Optional[int] = Field(default=None, foreign_key="change_events.id", index=True)

    # Pipeline state
    pipeline_status: str = PipelineStatus.RECEIVED.value
    error_message: Optional[str] = None

    # Slack
    slack_message_ts: Optional[str] = None


class CostLedger(SQLModel, table=True):
    __tablename__ = "cost_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True)  # YYYY-MM-DD
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    event_id: Optional[int] = Field(default=None, foreign_key="change_events.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
