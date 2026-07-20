"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"


class Settings(BaseSettings):
    """Validated server settings.

    Environment variable names match the upper-case form of each field name. Tests can
    pass ``_env_file=None`` to guarantee that no developer ``.env`` file is read.
    """

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        validate_default=True,
    )

    app_name: str = "Shiguang API"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    app_timezone: str = "Asia/Shanghai"
    database_url: str = "sqlite+aiosqlite:///./data/shiguang.db"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "APP_TIMEZONE must be a valid IANA timezone, such as Asia/Shanghai"
            ) from exc
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError as exc:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy database URL") from exc
        if url.drivername != "sqlite+aiosqlite":
            raise ValueError("DATABASE_URL must use sqlite+aiosqlite during M0")
        return value


def load_settings() -> Settings:
    """Load server settings, skipping dotenv when the process explicitly runs as tests."""

    env_file: Path | None = (
        None if os.environ.get("APP_ENV", "").lower() == "test" else DEFAULT_ENV_FILE
    )
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
