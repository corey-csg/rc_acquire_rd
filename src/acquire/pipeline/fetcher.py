from __future__ import annotations

import structlog
import httpx

from acquire.config import get_settings

logger = structlog.get_logger()


async def fetch_diff(watch_uuid: str) -> tuple[str | None, str | None]:
    """Fetch the latest snapshot and diff from changedetection.io.

    Returns (diff_text, snapshot_text). Either may be None if unavailable.
    """
    settings = get_settings()
    base = settings.cdio_base_url.rstrip("/")
    headers = {"x-api-key": settings.cdio_api_key}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch latest snapshot
        snapshot_text = None
        try:
            resp = await client.get(
                f"{base}/api/v1/watch/{watch_uuid}/history/latest",
                headers=headers,
            )
            if resp.status_code == 200:
                snapshot_text = resp.text
            else:
                logger.warning("snapshot_fetch_failed", status=resp.status_code, uuid=watch_uuid)
        except httpx.HTTPError as e:
            logger.error("snapshot_fetch_error", error=str(e), uuid=watch_uuid)

        # Fetch history timestamps to get diff between last two
        diff_text = None
        try:
            resp = await client.get(
                f"{base}/api/v1/watch/{watch_uuid}/history",
                headers=headers,
            )
            if resp.status_code == 200:
                history = resp.json()
                timestamps = sorted(history.keys())
                if len(timestamps) >= 2:
                    # Get the two most recent snapshots and diff them
                    prev_ts = timestamps[-2]
                    curr_ts = timestamps[-1]
                    prev_resp = await client.get(
                        f"{base}/api/v1/watch/{watch_uuid}/history/{prev_ts}",
                        headers=headers,
                    )
                    curr_resp = await client.get(
                        f"{base}/api/v1/watch/{watch_uuid}/history/{curr_ts}",
                        headers=headers,
                    )
                    if prev_resp.status_code == 200 and curr_resp.status_code == 200:
                        prev_text = prev_resp.text
                        curr_text = curr_resp.text
                        # Simple line-based diff
                        diff_text = _compute_diff(prev_text, curr_text)
                elif len(timestamps) == 1:
                    # Only one snapshot - use it as the diff (first detection)
                    diff_text = snapshot_text
        except httpx.HTTPError as e:
            logger.error("history_fetch_error", error=str(e), uuid=watch_uuid)

    return diff_text, snapshot_text


def _compute_diff(old: str, new: str) -> str:
    """Compute a simple diff showing added and removed lines."""
    old_lines = set(old.splitlines())
    new_lines = new.splitlines()

    diff_parts = []
    for line in new_lines:
        if line not in old_lines:
            diff_parts.append(f"+ {line}")

    removed = old_lines - set(new_lines)
    for line in sorted(removed):
        diff_parts.append(f"- {line}")

    return "\n".join(diff_parts) if diff_parts else ""
