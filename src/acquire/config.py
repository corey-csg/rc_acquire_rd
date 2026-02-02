from __future__ import annotations

from pathlib import Path
from functools import lru_cache

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# In Docker, the package is installed to site-packages but config lives at /app/config.
# Fall back to the source-tree-relative path for local development.
_docker_config = Path("/app/config")
CONFIG_DIR = _docker_config if _docker_config.exists() else ROOT_DIR / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # changedetection.io
    cdio_base_url: str = "http://localhost:5000"
    cdio_api_key: str = ""

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4"

    # Slack
    slack_webhook_url: str = ""

    # Budget
    daily_budget_usd: float = 5.00

    # Webhook auth
    webhook_secret: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///data/acquire.db"

    # Pipeline
    min_diff_length: int = 50

    def load_yaml_config(self) -> dict:
        settings_path = CONFIG_DIR / "settings.yaml"
        if settings_path.exists():
            with open(settings_path) as f:
                return yaml.safe_load(f)
        return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
