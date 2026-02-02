from __future__ import annotations

import json

import structlog
import httpx

from acquire.config import get_settings
from acquire.models.db import ChangeEvent

logger = structlog.get_logger()


def _build_slack_blocks(event: ChangeEvent) -> list[dict]:
    """Build Slack Block Kit blocks for a change event notification."""
    yaml_config = get_settings().load_yaml_config()
    urgency_emoji = yaml_config.get("slack", {}).get("urgency_emoji", {})

    urgency = event.urgency or "MEDIUM"
    emoji = urgency_emoji.get(urgency, ":large_blue_circle:")
    classification = event.classification or "UNKNOWN"

    divider = {"type": "divider"}

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {classification} - {urgency} Urgency",
            },
        },
        divider,
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":link: *Source:* <{event.watch_url}|{_truncate(event.watch_url, 80)}>",
            },
        },
    ]

    if event.summary:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary*\n{event.summary}",
            },
        })

    blocks.append(divider)

    if event.recommended_actions:
        try:
            actions = json.loads(event.recommended_actions)
        except (json.JSONDecodeError, TypeError):
            actions = []

        if actions:
            action_text = "\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1))
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":clipboard: *Next Steps*\n{action_text}",
                },
            })

    if event.key_dates:
        try:
            dates = json.loads(event.key_dates)
        except (json.JSONDecodeError, TypeError):
            dates = []

        if dates:
            date_text = "\n".join(f"  - {d}" for d in dates)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":calendar: *Key Dates*\n{date_text}",
                },
            })

    if event.relevant_agencies:
        try:
            agencies = json.loads(event.relevant_agencies)
        except (json.JSONDecodeError, TypeError):
            agencies = []

        if agencies:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":office: *Agencies*\n  {'  |  '.join(agencies)}",
                },
            })

    blocks.append(divider)

    # Context block: single line with pipe separators
    context_parts = []
    if event.parent_event_id is not None:
        context_parts.append(f"Discovered via Event #{event.parent_event_id}")
    if event.classification_confidence is not None:
        context_parts.append(f"Confidence: {event.classification_confidence:.0%}")
    if event.enrichment_model:
        context_parts.append(event.enrichment_model)
    context_parts.append(f"Event #{event.id}")

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "  |  ".join(context_parts),
            },
        ],
    })

    return blocks


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


async def notify_slack(event: ChangeEvent) -> str | None:
    """Send a Slack notification for a change event. Returns message_ts if successful."""
    settings = get_settings()
    if not settings.slack_webhook_url:
        logger.warning("slack_not_configured", event_id=event.id)
        return None

    blocks = _build_slack_blocks(event)
    urgency = event.urgency or "MEDIUM"
    classification = event.classification or "UNKNOWN"
    payload = {
        "text": f"{classification} [{urgency}]: {event.summary or event.watch_url}",
        "blocks": blocks,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(settings.slack_webhook_url, json=payload)
        if resp.status_code == 200:
            logger.info("slack_sent", event_id=event.id)
            return resp.text  # Webhook returns "ok"
        else:
            logger.error(
                "slack_failed",
                event_id=event.id,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return None
