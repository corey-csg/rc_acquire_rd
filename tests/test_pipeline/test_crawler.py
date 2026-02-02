from __future__ import annotations

import pytest
import respx
import httpx

from acquire.pipeline.crawler import html_to_text, fetch_page_text


class TestHtmlToText:
    def test_basic_html(self):
        html = "<html><body><p>Hello world</p></body></html>"
        assert "Hello world" in html_to_text(html)

    def test_strips_script_and_style(self):
        html = """
        <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <script>alert('hi');</script>
            <p>Visible text</p>
            <noscript>No JS</noscript>
            <p>More text</p>
        </body>
        </html>
        """
        text = html_to_text(html)
        assert "Visible text" in text
        assert "More text" in text
        assert "alert" not in text
        assert "color: red" not in text
        assert "No JS" not in text

    def test_empty_html(self):
        assert html_to_text("") == ""

    def test_plain_text(self):
        text = html_to_text("Just plain text, no HTML tags")
        assert "Just plain text" in text

    def test_nested_elements(self):
        html = "<div><p>Outer <span>inner</span> text</p></div>"
        text = html_to_text(html)
        assert "Outer" in text
        assert "inner" in text
        assert "text" in text


class TestFetchPageText:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_html_page(self):
        respx.get("https://example.gov/nofo").mock(
            return_value=httpx.Response(
                200,
                text="<html><body><p>Grant opportunity details</p></body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )

        result = await fetch_page_text("https://example.gov/nofo")
        assert result is not None
        assert "Grant opportunity details" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_plain_text(self):
        respx.get("https://example.gov/data.txt").mock(
            return_value=httpx.Response(
                200,
                text="Plain text content here",
                headers={"content-type": "text/plain"},
            )
        )

        result = await fetch_page_text("https://example.gov/data.txt")
        assert result is not None
        assert "Plain text content here" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_truncates_to_max_chars(self):
        long_text = "A" * 20000
        respx.get("https://example.gov/long").mock(
            return_value=httpx.Response(
                200,
                text=f"<html><body><p>{long_text}</p></body></html>",
                headers={"content-type": "text/html"},
            )
        )

        result = await fetch_page_text("https://example.gov/long", max_chars=100)
        assert result is not None
        assert len(result) == 100

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_none_on_error(self):
        respx.get("https://example.gov/404").mock(
            return_value=httpx.Response(404)
        )

        result = await fetch_page_text("https://example.gov/404")
        assert result is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_none_on_timeout(self):
        respx.get("https://example.gov/slow").mock(
            side_effect=httpx.ConnectTimeout("Timed out")
        )

        result = await fetch_page_text("https://example.gov/slow")
        assert result is None
