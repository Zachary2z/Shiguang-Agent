"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Literal, Self
from unicodedata import category
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.domain.places.matching import PlaceMatchingPolicy
from app.storage_policy import (
    DEFAULT_STORAGE_ALLOWED_CONTENT_TYPES,
    DEFAULT_STORAGE_MAX_FILE_SIZE_BYTES,
    MAX_STORAGE_MAX_FILE_SIZE_BYTES,
    SUPPORTED_STORAGE_CONTENT_TYPES,
)
from nanobot_core.agent.limits import MAX_RUN_TIMEOUT_SECONDS, MAX_TOOL_CALLS_PER_RUN
from nanobot_core.providers import StructuredOutputMode

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_AMAP_BASE_URL = "https://restapi.amap.com"
DEFAULT_MODEL_TIMEOUT_SECONDS = 75.0
MAX_MODEL_TIMEOUT_SECONDS = 75.0
MAX_AMAP_TIMEOUT_SECONDS = 30.0
MAX_AMAP_RETRIES = 1
MAX_AMAP_RETRY_AFTER_SECONDS = 5.0


class ModelConfigurationError(ValueError):
    """A fixed, secret-safe model configuration failure."""


class AmapConfigurationError(Exception):
    """A fixed, secret-safe Amap configuration failure."""


class StorageConfigurationError(Exception):
    """A fixed local storage configuration failure without path disclosure."""


@dataclass(frozen=True, slots=True)
class ModelProviderSettings:
    """Real-provider settings; timeout covers one complete SDK call wall clock."""

    api_base: str
    api_key: SecretStr
    model_name: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class AmapProviderSettings:
    """Complete settings required to construct the real Amap provider."""

    api_key: SecretStr
    base_url: str
    timeout_seconds: float
    max_retries: int
    retry_after_max_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_key", _validate_amap_api_key(self.api_key))
        object.__setattr__(self, "base_url", _normalize_amap_base_url(self.base_url))
        object.__setattr__(
            self,
            "timeout_seconds",
            _validate_amap_timeout_seconds(self.timeout_seconds),
        )
        object.__setattr__(
            self,
            "max_retries",
            _validate_amap_max_retries(self.max_retries),
        )
        object.__setattr__(
            self,
            "retry_after_max_seconds",
            _validate_amap_retry_after_max_seconds(self.retry_after_max_seconds),
        )


@dataclass(frozen=True, slots=True)
class StorageProviderSettings:
    """Complete, provider-neutral limits for the local private storage adapter."""

    private_root: Path = field(repr=False)
    max_file_size_bytes: int
    allowed_content_types: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.private_root, Path):
            raise StorageConfigurationError("STORAGE_PRIVATE_ROOT must be a filesystem path")
        if (
            type(self.max_file_size_bytes) is not int
            or self.max_file_size_bytes < 1
            or self.max_file_size_bytes > MAX_STORAGE_MAX_FILE_SIZE_BYTES
        ):
            raise StorageConfigurationError(
                "STORAGE_MAX_FILE_SIZE_BYTES must be an integer from 1 to "
                f"{MAX_STORAGE_MAX_FILE_SIZE_BYTES}"
            )
        if (
            not isinstance(self.allowed_content_types, frozenset)
            or not self.allowed_content_types
            or not self.allowed_content_types <= SUPPORTED_STORAGE_CONTENT_TYPES
        ):
            raise StorageConfigurationError(
                "STORAGE_ALLOWED_CONTENT_TYPES must contain only supported private file types"
            )


_AMAP_API_KEY_ERROR = "AMAP_API_KEY must be a non-blank SecretStr"
_AMAP_BASE_URL_ERROR = (
    "AMAP_BASE_URL must use the fixed official Amap Web Service origin"
)
_AMAP_TIMEOUT_ERROR = (
    f"AMAP_TIMEOUT_SECONDS must be a finite number in (0, {MAX_AMAP_TIMEOUT_SECONDS:g}]"
)
_AMAP_MAX_RETRIES_ERROR = (
    f"AMAP_MAX_RETRIES must be an integer from 0 to {MAX_AMAP_RETRIES}"
)
_AMAP_RETRY_AFTER_ERROR = (
    "AMAP_RETRY_AFTER_MAX_SECONDS must be a finite number in "
    f"[0, {MAX_AMAP_RETRY_AFTER_SECONDS:g}]"
)


def _validate_amap_api_key(value: object) -> SecretStr:
    if not isinstance(value, SecretStr) or not value.get_secret_value().strip():
        raise AmapConfigurationError(_AMAP_API_KEY_ERROR)
    return value


def _parse_settings_amap_api_key(value: object) -> SecretStr | None:
    if value is None or isinstance(value, SecretStr):
        return value
    if isinstance(value, str):
        return SecretStr(value)
    raise AmapConfigurationError(_AMAP_API_KEY_ERROR)


def _reject_amap_boolean(value: object, *, error_message: str) -> object:
    if isinstance(value, bool):
        raise AmapConfigurationError(error_message)
    return value


def _parse_settings_amap_number(
    value: object,
    *,
    error_message: str,
    validator: Callable[[object], float],
) -> float:
    if isinstance(value, str):
        try:
            parsed_value: float | None = float(value)
        except ValueError:
            parsed_value = None
        if parsed_value is None:
            raise AmapConfigurationError(error_message)
        value = parsed_value
    return validator(value)


def _validate_amap_timeout_seconds(value: object) -> float:
    _reject_amap_boolean(value, error_message=_AMAP_TIMEOUT_ERROR)
    if (
        not isinstance(value, int | float)
        or not isfinite(value)
        or value <= 0
        or value > MAX_AMAP_TIMEOUT_SECONDS
    ):
        raise AmapConfigurationError(_AMAP_TIMEOUT_ERROR)
    return float(value)


def _validate_amap_max_retries(value: object) -> int:
    if type(value) is not int or value < 0 or value > MAX_AMAP_RETRIES:
        raise AmapConfigurationError(_AMAP_MAX_RETRIES_ERROR)
    return value


def _parse_settings_amap_max_retries(value: object) -> int:
    if isinstance(value, str):
        try:
            parsed_value: int | None = int(value)
        except ValueError:
            parsed_value = None
        if parsed_value is None:
            raise AmapConfigurationError(_AMAP_MAX_RETRIES_ERROR)
        value = parsed_value
    return _validate_amap_max_retries(value)


def _validate_amap_retry_after_max_seconds(value: object) -> float:
    _reject_amap_boolean(value, error_message=_AMAP_RETRY_AFTER_ERROR)
    if (
        not isinstance(value, int | float)
        or not isfinite(value)
        or value < 0
        or value > MAX_AMAP_RETRY_AFTER_SECONDS
    ):
        raise AmapConfigurationError(_AMAP_RETRY_AFTER_ERROR)
    return float(value)


def _normalize_amap_base_url(value: str) -> str:
    """Accept only Amap's canonical Web Service origin and return that origin."""

    invalid_character = not isinstance(value, str) or not value or any(
        character.isspace()
        or category(character).startswith("C")
        or character == "\\"
        for character in value
    )
    valid = False
    if not invalid_character:
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname == "restapi.amap.com"
                and parsed.netloc.casefold() == "restapi.amap.com"
                and parsed.port is None
                and parsed.username is None
                and parsed.password is None
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
                and "?" not in value
                and "#" not in value
            )
        except ValueError:
            valid = False
    if not valid:
        raise AmapConfigurationError(_AMAP_BASE_URL_ERROR)
    return DEFAULT_AMAP_BASE_URL


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
    model_timeout_seconds: float | None = DEFAULT_MODEL_TIMEOUT_SECONDS
    model_structured_output_mode: Literal[
        "none",
        "json_schema",
        "json_object",
    ] = "none"
    model_input_price_per_million_tokens: Decimal | None = None
    model_output_price_per_million_tokens: Decimal | None = None
    model_cost_currency: str = "CNY"
    model_pricing_source: str = "configured_model_rates"
    agent_max_tool_calls: int = MAX_TOOL_CALLS_PER_RUN
    agent_timeout_seconds: float = MAX_RUN_TIMEOUT_SECONDS
    amap_api_key: SecretStr | None = None
    amap_base_url: str = DEFAULT_AMAP_BASE_URL
    amap_timeout_seconds: float = 5.0
    amap_max_retries: int = MAX_AMAP_RETRIES
    amap_retry_after_max_seconds: float = 1.0
    place_match_unique_score: float = 75.0
    place_match_minimum_score_gap: float = 12.0
    place_match_candidate_score: float = 35.0
    storage_private_root: Path = Field(default=Path("./data/private"), repr=False)
    storage_max_file_size_bytes: int = DEFAULT_STORAGE_MAX_FILE_SIZE_BYTES
    storage_allowed_content_types: str = ",".join(DEFAULT_STORAGE_ALLOWED_CONTENT_TYPES)

    @field_validator("amap_api_key", mode="before")
    @classmethod
    def parse_amap_api_key(cls, value: object) -> SecretStr | None:
        return _parse_settings_amap_api_key(value)

    @field_validator("amap_base_url", mode="before")
    @classmethod
    def validate_amap_base_url_type(cls, value: object) -> str:
        if not isinstance(value, str):
            raise AmapConfigurationError(_AMAP_BASE_URL_ERROR)
        return value

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
        if url.drivername not in {"sqlite+aiosqlite", "postgresql+asyncpg"}:
            raise ValueError(
                "DATABASE_URL must use postgresql+asyncpg or sqlite+aiosqlite"
            )
        return value

    @field_validator("model_timeout_seconds", mode="before")
    @classmethod
    def reject_boolean_model_timeout(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError(
                "MODEL_TIMEOUT_SECONDS must be a finite number in "
                f"(0, {MAX_MODEL_TIMEOUT_SECONDS:g}]"
            )
        return value

    @field_validator("model_timeout_seconds")
    @classmethod
    def validate_model_timeout(cls, value: float | None) -> float | None:
        if value is not None and (
            not isfinite(value)
            or value <= 0
            or value > MAX_MODEL_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "MODEL_TIMEOUT_SECONDS must be a finite number in "
                f"(0, {MAX_MODEL_TIMEOUT_SECONDS:g}]"
            )
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

    @field_validator("amap_timeout_seconds", mode="before")
    @classmethod
    def parse_amap_timeout(cls, value: object) -> object:
        return _parse_settings_amap_number(
            value,
            error_message=_AMAP_TIMEOUT_ERROR,
            validator=_validate_amap_timeout_seconds,
        )

    @field_validator("amap_max_retries", mode="before")
    @classmethod
    def parse_amap_retries(cls, value: object) -> object:
        return _parse_settings_amap_max_retries(value)

    @field_validator("amap_retry_after_max_seconds", mode="before")
    @classmethod
    def parse_amap_retry_after_max(cls, value: object) -> object:
        return _parse_settings_amap_number(
            value,
            error_message=_AMAP_RETRY_AFTER_ERROR,
            validator=_validate_amap_retry_after_max_seconds,
        )

    @field_validator(
        "place_match_unique_score",
        "place_match_minimum_score_gap",
        "place_match_candidate_score",
        mode="before",
    )
    @classmethod
    def validate_place_match_threshold_type(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("place matching thresholds must be finite numbers in (0, 100]")
        return value

    @field_validator(
        "place_match_unique_score",
        "place_match_minimum_score_gap",
        "place_match_candidate_score",
    )
    @classmethod
    def validate_place_match_threshold(cls, value: float) -> float:
        if not isfinite(value) or value <= 0 or value > 100:
            raise ValueError("place matching thresholds must be finite numbers in (0, 100]")
        return value

    @model_validator(mode="after")
    def validate_place_match_threshold_order(self) -> Self:
        if self.place_match_candidate_score > self.place_match_unique_score:
            raise ValueError(
                "PLACE_MATCH_CANDIDATE_SCORE cannot exceed PLACE_MATCH_UNIQUE_SCORE"
            )
        return self

    @model_validator(mode="after")
    def require_postgresql_in_production(self) -> Self:
        if (
            self.app_env == "production"
            and make_url(self.database_url).drivername != "postgresql+asyncpg"
        ):
            raise ValueError("production DATABASE_URL must use postgresql+asyncpg")
        return self

    @field_validator("storage_max_file_size_bytes", mode="before")
    @classmethod
    def validate_storage_size_type(cls, value: object) -> object:
        if isinstance(value, bool):
            raise StorageConfigurationError(
                "STORAGE_MAX_FILE_SIZE_BYTES must be an integer from 1 to "
                f"{MAX_STORAGE_MAX_FILE_SIZE_BYTES}"
            )
        return value

    @field_validator("storage_max_file_size_bytes")
    @classmethod
    def validate_storage_size(cls, value: int) -> int:
        if value < 1 or value > MAX_STORAGE_MAX_FILE_SIZE_BYTES:
            raise StorageConfigurationError(
                "STORAGE_MAX_FILE_SIZE_BYTES must be an integer from 1 to "
                f"{MAX_STORAGE_MAX_FILE_SIZE_BYTES}"
            )
        return value

    @field_validator("storage_allowed_content_types", mode="before")
    @classmethod
    def normalize_storage_content_types(cls, value: object) -> str:
        if not isinstance(value, str):
            raise StorageConfigurationError(
                "STORAGE_ALLOWED_CONTENT_TYPES must contain only supported private file types"
            )
        parts = tuple(part.strip().lower() for part in value.split(",") if part.strip())
        allowed = frozenset(parts)
        if (
            not parts
            or len(allowed) != len(parts)
            or not allowed <= SUPPORTED_STORAGE_CONTENT_TYPES
        ):
            raise StorageConfigurationError(
                "STORAGE_ALLOWED_CONTENT_TYPES must contain only supported private file types"
            )
        return ",".join(sorted(allowed))

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

    def require_amap_provider(self) -> AmapProviderSettings:
        """Return real Amap settings only when the adapter is explicitly constructed."""

        api_key = _validate_amap_api_key(self.amap_api_key)

        return AmapProviderSettings(
            api_key=api_key,
            base_url=self.amap_base_url,
            timeout_seconds=self.amap_timeout_seconds,
            max_retries=self.amap_max_retries,
            retry_after_max_seconds=self.amap_retry_after_max_seconds,
        )

    def extraction_structured_output_mode(self) -> StructuredOutputMode | None:
        """Return only the explicitly configured, externally verified capability."""

        if self.model_structured_output_mode == "none":
            return None
        return StructuredOutputMode(self.model_structured_output_mode)

    def place_matching_policy(self) -> PlaceMatchingPolicy:
        """Build the one validated server-side place matching policy."""

        return PlaceMatchingPolicy(
            unique_match_score=self.place_match_unique_score,
            minimum_score_gap=self.place_match_minimum_score_gap,
            candidate_score=self.place_match_candidate_score,
        )

    def storage_provider_settings(self) -> StorageProviderSettings:
        """Build the one validated local private storage configuration."""

        return StorageProviderSettings(
            private_root=self.storage_private_root,
            max_file_size_bytes=self.storage_max_file_size_bytes,
            allowed_content_types=frozenset(
                self.storage_allowed_content_types.split(",")
            ),
        )


def load_settings() -> Settings:
    """Load server settings, skipping dotenv when the process explicitly runs as tests."""

    env_file: Path | None = (
        None if os.environ.get("APP_ENV", "").lower() == "test" else DEFAULT_ENV_FILE
    )
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
