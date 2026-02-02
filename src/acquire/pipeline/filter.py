from __future__ import annotations

from acquire.config import get_settings


ENRICH_CLASSIFICATIONS = {"RFI", "RFP", "ACTIONABLE"}
NOTIFY_CLASSIFICATIONS = {"RFI", "RFP", "ACTIONABLE"}


def should_enrich(classification: str) -> bool:
    """Return True if this classification warrants LLM enrichment."""
    yaml_config = get_settings().load_yaml_config()
    allowed = yaml_config.get("pipeline", {}).get("classifications_to_enrich", list(ENRICH_CLASSIFICATIONS))
    return classification.upper() in {c.upper() for c in allowed}


def should_notify(classification: str) -> bool:
    """Return True if this classification warrants Slack notification."""
    yaml_config = get_settings().load_yaml_config()
    allowed = yaml_config.get("pipeline", {}).get("classifications_to_notify", list(NOTIFY_CLASSIFICATIONS))
    return classification.upper() in {c.upper() for c in allowed}


def is_diff_too_small(diff_text: str | None) -> bool:
    """Return True if the diff is too small to be meaningful."""
    if not diff_text:
        return True
    settings = get_settings()
    return len(diff_text.strip()) < settings.min_diff_length
