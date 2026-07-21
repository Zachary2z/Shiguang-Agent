"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from nanobot_core.agent.limits import MAX_RUN_TIMEOUT_SECONDS, MAX_TOOL_CALLS_PER_RUN

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"


class ModelConfigurationError(ValueError):
    """A fixed, secret-safe model configuration failure."""


@dataclass(frozen=True, slots=True)
class ModelProviderSettings:
    """Complete settings required to construct the real model provider."""

    api_base: str
    api_key: SecretStr
    model_name: str
    timeout_seconds: float


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
    model_api_base: str | None = None
    model_api_key: SecretStr | None = None
    model_name: str | None = None
    model_timeout_seconds: float | None = None
    model_input_price_per_million_tokens: Decimal | None = None
    model_output_price_per_million_tokens: Decimal | None = None
    model_cost_currency: str = "CNY"
    model_pricing_source: str = "configured_model_rates"
    agent_max_tool_calls: int = MAX_TOOL_CALLS_PER_RUN
    agent_timeout_seconds: float = MAX_RUN_TIMEOUT_SECONDS

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

    @field_validator("model_timeout_seconds", mode="before")
    @classmethod
    def reject_boolean_model_timeout(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("MODEL_TIMEOUT_SECONDS must be a finite positive number")
        return value

    @field_validator("model_timeout_seconds")
    @classmethod
    def validate_model_timeout(cls, value: float | None) -> float | None:
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError("MODEL_TIMEOUT_SECONDS must be a finite positive number")
        return value

    @field_validator(
        "model_input_price_per_million_tokens",
        "model_output_price_per_million_tokens",
        mode="before",
    )
    @classmethod
    def validate_model_price(cls, value: object) -> object:
        if value is None:
            return value
        if isinstance(value, bool | float):
            raise ValueError("model token prices must be finite non-negative decimals")
        try:
            decimal_value = Decimal(value)  # type: ignore[arg-type]
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(
                "model token prices must be finite non-negative decimals"
            ) from exc
        if not decimal_value.is_finite() or decimal_value < 0:
            raise ValueError("model token prices must be finite non-negative decimals")
        return decimal_value

    @field_validator("model_cost_currency")
    @classmethod
    def validate_model_cost_currency(cls, value: str) -> str:
        if len(value) != 3 or not value.isascii() or not value.isalpha() or not value.isupper():
            raise ValueError("MODEL_COST_CURRENCY must be a three-letter uppercase code")
        return value

    @field_validator("model_pricing_source")
    @classmethod
    def validate_model_pricing_source(cls, value: str) -> str:
        if not value or len(value) > 64 or not all(
            character.isalnum() or character in "._:-" for character in value
        ):
            raise ValueError("MODEL_PRICING_SOURCE must be a safe label up to 64 characters")
        return value

    @field_validator("agent_max_tool_calls", mode="before")
    @classmethod
    def reject_boolean_agent_max_tool_calls(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError(
                "AGENT_MAX_TOOL_CALLS must be an integer from 1 to "
                f"{MAX_TOOL_CALLS_PER_RUN}"
            )
        return value

    @field_validator("agent_max_tool_calls")
    @classmethod
    def validate_agent_max_tool_calls(cls, value: int) -> int:
        if value < 1 or value > MAX_TOOL_CALLS_PER_RUN:
            raise ValueError(
                "AGENT_MAX_TOOL_CALLS must be an integer from 1 to "
                f"{MAX_TOOL_CALLS_PER_RUN}"
            )
        return value

    @field_validator("agent_timeout_seconds", mode="before")
    @classmethod
    def reject_boolean_agent_timeout(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError(
                "AGENT_TIMEOUT_SECONDS must be a finite number in "
                f"(0, {MAX_RUN_TIMEOUT_SECONDS:g}]"
            )
        return value

    @field_validator("agent_timeout_seconds")
    @classmethod
    def validate_agent_timeout(cls, value: float) -> float:
        if not isfinite(value) or value <= 0 or value > MAX_RUN_TIMEOUT_SECONDS:
            raise ValueError(
                "AGENT_TIMEOUT_SECONDS must be a finite number in "
                f"(0, {MAX_RUN_TIMEOUT_SECONDS:g}]"
            )
        return value

    def require_model_provider(self) -> ModelProviderSettings:
        """Return complete real-provider settings only when explicitly requested."""

        missing: list[str] = []
        api_base = self.model_api_base.strip() if self.model_api_base else ""
        api_key = self.model_api_key
        model_name = self.model_name.strip() if self.model_name else ""
        timeout_seconds = self.model_timeout_seconds

        if not api_base:
            missing.append("MODEL_API_BASE")
        if api_key is None or not api_key.get_secret_value().strip():
            missing.append("MODEL_API_KEY")
        if not model_name:
            missing.append("MODEL_NAME")
        if timeout_seconds is None:
            missing.append("MODEL_TIMEOUT_SECONDS")
        if missing:
            names = ", ".join(missing)
            raise ModelConfigurationError(f"Missing model provider configuration: {names}")

        try:
            parsed_base = urlsplit(api_base)
            parsed_port = parsed_base.port
            valid_base = (
                parsed_base.scheme in {"http", "https"}
                and parsed_base.hostname is not None
                and (parsed_port is None or parsed_port > 0)
                and parsed_base.username is None
                and parsed_base.password is None
                and not parsed_base.query
                and not parsed_base.fragment
            )
        except ValueError:
            valid_base = False
        if not valid_base:
            raise ModelConfigurationError(
                "MODEL_API_BASE must be an HTTP(S) URL without credentials, query, or fragment"
            )

        # The missing-value branch above proves these values are complete.
        assert api_key is not None
        assert timeout_seconds is not None
        return ModelProviderSettings(
            api_base=api_base,
            api_key=api_key,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )


def load_settings() -> Settings:
    """Load server settings, skipping dotenv when the process explicitly runs as tests."""

    env_file: Path | None = (
        None if os.environ.get("APP_ENV", "").lower() == "test" else DEFAULT_ENV_FILE
    )
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
