from __future__ import annotations

import json
import re

import structlog
import httpx

from acquire.config import get_settings

logger = structlog.get_logger()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _extract_json(text: str) -> dict | str:
    """Try multiple strategies to parse JSON from LLM output."""
    if not text or not text.strip():
        return text

    # 1. Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Strip markdown code fences
    stripped = re.sub(r"^[ \t]*```(?:json)?[ \t]*\n?", "", text.strip(), count=1)
    stripped = re.sub(r"\n?[ \t]*```[ \t]*$", "", stripped, count=1)
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Find first { ... } block in text
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, TypeError):
            pass

    logger.warning("llm_json_parse_failed", content=text[:300])
    return text


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.1,
    response_format: dict | None = None,
) -> dict:
    """Call OpenRouter chat completion API.

    Returns dict with keys: content, model, prompt_tokens, completion_tokens, total_tokens.
    """
    settings = get_settings()
    model = model or settings.openrouter_model

    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        body["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://rc-rd-acquire.app",
        "X-Title": "RC/RD Acquire",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(OPENROUTER_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]
    usage = data.get("usage", {})

    content = choice["message"]["content"]

    # Try to parse JSON from content
    if response_format and response_format.get("type") == "json_object":
        content = _extract_json(content)

    return {
        "content": content,
        "model": data.get("model", model),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
