#!/usr/bin/env python3
"""Fire a fake webhook to test the pipeline locally."""

import argparse
import httpx


def main():
    parser = argparse.ArgumentParser(description="Simulate a changedetection.io webhook")
    parser.add_argument("--url", default="http://localhost:8000/webhooks/change")
    parser.add_argument("--watch-uuid", default="test-uuid-001")
    parser.add_argument("--watch-url", default="https://www.usda.gov/reconnect")
    parser.add_argument("--secret", default="")
    args = parser.parse_args()

    headers = {}
    if args.secret:
        headers["x-webhook-secret"] = args.secret

    payload = {
        "watch_uuid": args.watch_uuid,
        "watch_url": args.watch_url,
    }

    resp = httpx.post(args.url, json=payload, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")


if __name__ == "__main__":
    main()
