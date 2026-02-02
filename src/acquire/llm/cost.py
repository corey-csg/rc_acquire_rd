from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from acquire.config import get_settings
from acquire.storage import repository

logger = structlog.get_logger()

# Approximate cost per 1M tokens for common models (input/output)
MODEL_COSTS: dict[str, tuple[float, float]] = {
    "moonshotai/kimi-k2.5": (1.0, 4.0),
    "deepseek/deepseek-v3.2": (0.50, 1.40),
    "anthropic/claude-sonnet-4": (3.0, 15.0),
    "anthropic/claude-3.5-sonnet": (3.0, 15.0),
    "anthropic/claude-3-haiku": (0.25, 1.25),
    "google/gemini-flash-1.5": (0.075, 0.30),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.0),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost based on model and token counts."""
    input_rate, output_rate = MODEL_COSTS.get(model, (3.0, 15.0))
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return round(cost, 6)


async def check_budget(session: AsyncSession) -> bool:
    """Return True if today's spend is under the daily budget."""
    settings = get_settings()
    spent = await repository.get_daily_spend(session)
    under = spent < settings.daily_budget_usd
    if not under:
        logger.warning("budget_exceeded", spent=spent, limit=settings.daily_budget_usd)
    return under


async def record_usage(
    session: AsyncSession,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    event_id: int | None = None,
) -> float:
    """Record token usage and return estimated cost."""
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    await repository.record_cost(
        session,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        event_id=event_id,
    )
    logger.info(
        "cost_recorded",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
    )
    return cost
