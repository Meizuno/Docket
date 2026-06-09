"""Application configuration via pydantic-settings.

Values load from environment variables (prefix ``DOCKET_``) or a .env
file, falling back to the defaults below. Validation is fail-fast: building
Settings (e.g. via get_settings at startup) raises ValidationError on any
invalid value rather than letting it surface later.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Base settings for Docket."""

    model_config = SettingsConfigDict(
        env_prefix="DOCKET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="docket", min_length=1)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/docket",
        min_length=1,
    )
    log_level: str = Field(default="INFO")

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise ValueError(f"log_level must be one of: {allowed}")
        return level


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance (raises on invalid config)."""
    return Settings()
