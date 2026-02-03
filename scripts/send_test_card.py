#!/usr/bin/env python3
"""Send a test Slack card to verify the new block layout."""

import json
import sys
import httpx

WEBHOOK_URL = sys.argv[1] if len(sys.argv) > 1 else None

if not WEBHOOK_URL:
    print("Usage: python scripts/send_test_card.py <slack-webhook-url>")
    sys.exit(1)

payload = {
    "text": "RFP [HIGH]: USDA announces $1.1B ReConnect Round 5 NOFO with deadline March 15 2026.",
    "blocks": [
        {"type": "header", "text": {"type": "plain_text", "text": ":warning: RFP - HIGH Urgency"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": ":link: *Source:* <https://www.usda.gov/reconnect|www.usda.gov/reconnect>"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Summary*\nUSDA announces $1.1B ReConnect Round 5 NOFO with deadline March 15 2026."}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": ":clipboard: *Next Steps*\n1. Register for industry day on Feb 20\n2. Review eligibility criteria in NOFO\n3. Prepare application with cost estimates"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": ":calendar: *Key Dates*\n  - 2026-03-15: Application deadline\n  - 2026-02-20: Industry day"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": ":office: *Agencies*\n  USDA  |  Rural Utilities Service"}},
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Confidence: 95%  |  deepseek/deepseek-v3.2  |  Event #42"}]},
    ],
}

resp = httpx.post(WEBHOOK_URL, json=payload)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
