from __future__ import annotations

from html.parser import HTMLParser

import structlog
import httpx

logger = structlog.get_logger()

SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "head"})


class _TextExtractor(HTMLParser):
    """Strip HTML to plain text, skipping script/style/noscript tags."""

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self) -> str:
        return "\n".join(self._pieces)


def html_to_text(html: str) -> str:
    """Convert HTML string to plain text."""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


async def fetch_page_text(url: str, max_chars: int = 8000) -> str | None:
    """Fetch a URL and return plain text content, or None on failure."""
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "RC-RD-Acquire/0.1 (Government Procurement Monitor)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            text = html_to_text(resp.text)
        else:
            text = resp.text

        return text[:max_chars] if text else None

    except Exception as e:
        logger.warning("page_fetch_failed", url=url, error=str(e)[:200])
        return None
