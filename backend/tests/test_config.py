"""Configuration loading and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

import app.config as config_module
from app.config import (
    AmapConfigurationError,
    ModelConfigurationError,
    Settings,
    load_settings,
)
from app.main import create_app


def test_dotenv_loading_can_be_explicitly_disabled(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "APP_ENV=production\nDATABASE_URL=not-a-valid-database-url\n",
        encoding="utf-8",
    )

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_explicit_settings_override_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        app_timezone="UTC",
        database_url="sqlite+aiosqlite:///:memory:",
        log_level="WARNING",
    )

    assert settings.app_timezone == "UTC"
    assert settings.log_level == "WARNING"


def test_test_environment_skips_configured_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DATABASE_URL=not-a-valid-database-url\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "DEFAULT_ENV_FILE", dotenv_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    settings = load_settings()

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_invalid_timezone_has_diagnostic_error() -> None:
    with pytest.raises(ValidationError, match="APP_TIMEZONE must be a valid IANA timezone"):
        Settings(
            _env_file=None,
            app_env="test",
            app_timezone="Mars/Olympus_Mons",
            database_url="sqlite+aiosqlite:///:memory:",
        )


def test_non_async_sqlite_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"must use sqlite\+aiosqlite during M0"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite:///./wrong-driver.db",
        )


def test_application_and_health_configuration_do_not_require_real_provider_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=None,
        model_api_key=None,
        model_name=None,
        model_timeout_seconds=None,
        amap_api_key=None,
    )

    app = create_app(settings)

    assert app.state.settings is settings


def test_complete_amap_configuration_is_deferred_and_secret_wrapped() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-amap-key",
        amap_timeout_seconds=8.5,
        amap_max_retries=1,
        amap_retry_after_max_seconds=2,
    )

    amap = settings.require_amap_provider()

    assert amap.base_url == "https://restapi.amap.com"
    assert isinstance(amap.api_key, SecretStr)
    assert amap.api_key.get_secret_value() == "fake-amap-key"
    assert amap.timeout_seconds == 8.5
    assert amap.max_retries == 1
    assert amap.retry_after_max_seconds == 2


def test_missing_amap_key_is_required_only_when_real_adapter_is_requested() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key=None,
    )

    with pytest.raises(AmapConfigurationError, match="AMAP_API_KEY"):
        settings.require_amap_provider()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://restapi.amap.com",
        "https://example.com",
        "https://restapi.amap.com.evil.example",
        "https://user:password@restapi.amap.com",
        "https://restapi.amap.com:443",
        "https://restapi.amap.com:8443",
        "https://restapi.amap.com:",
        "https://restapi.amap.com:0",
        "https://restapi.amap.com/v3/place/text",
        "https://restapi.amap.com?key=unsafe",
        "https://restapi.amap.com?",
        "https://restapi.amap.com#unsafe",
        "https://restapi.amap.com#",
        "https://restapi.amap.com\n.evil.example",
        "https://restapi.amap.com\x00.evil.example",
        "https://restapi.amap.com\\@evil.example",
        "https://[broken",
        " https://restapi.amap.com",
        "not-a-url",
    ],
)
def test_invalid_amap_base_url_is_rejected_without_echoing_value(base_url: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-amap-key",
        amap_base_url=base_url,
    )

    with pytest.raises(AmapConfigurationError) as exc_info:
        settings.require_amap_provider()

    assert base_url not in str(exc_info.value)


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://restapi.amap.com", "https://restapi.amap.com"),
        ("https://restapi.amap.com/", "https://restapi.amap.com"),
        ("https://RESTAPI.AMAP.COM/", "https://restapi.amap.com"),
    ],
)
def test_official_amap_base_url_is_canonically_normalized(
    base_url: str,
    expected: str,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key="fake-amap-key",
        amap_base_url=base_url,
    )

    assert settings.require_amap_provider().base_url == expected


@pytest.mark.parametrize("timeout", [0, 30.1, -1, float("nan"), float("inf"), True])
def test_invalid_amap_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(ValidationError, match="AMAP_TIMEOUT_SECONDS"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            amap_timeout_seconds=timeout,
        )


@pytest.mark.parametrize("retries", [-1, 2, True])
def test_amap_retries_have_one_extra_attempt_hard_limit(retries: int) -> None:
    with pytest.raises(ValidationError, match="AMAP_MAX_RETRIES"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            amap_max_retries=retries,
        )


@pytest.mark.parametrize("cap", [-1, 5.1, float("nan"), float("inf"), True])
def test_amap_retry_after_cap_is_bounded(cap: float) -> None:
    with pytest.raises(ValidationError, match="AMAP_RETRY_AFTER_MAX_SECONDS"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            amap_retry_after_max_seconds=cap,
        )


def test_complete_model_configuration_is_returned_with_secret_type() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base="https://model.example.test/compatible-mode/v1",
        model_api_key="fake-test-key",
        model_name="configured-test-model",
        model_timeout_seconds=12.5,
    )

    model = settings.require_model_provider()

    assert model.api_base == "https://model.example.test/compatible-mode/v1"
    assert isinstance(model.api_key, SecretStr)
    assert model.api_key.get_secret_value() == "fake-test-key"
    assert model.model_name == "configured-test-model"
    assert model.timeout_seconds == 12.5


def test_missing_model_configuration_is_deferred_and_secret_safe() -> None:
    secret = "fake-key-that-must-not-leak"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=None,
        model_api_key=secret,
        model_name=" ",
        model_timeout_seconds=None,
    )

    with pytest.raises(ModelConfigurationError) as exc_info:
        settings.require_model_provider()

    error = str(exc_info.value)
    assert "MODEL_API_BASE" in error
    assert "MODEL_NAME" in error
    assert "MODEL_TIMEOUT_SECONDS" in error
    assert secret not in error


@pytest.mark.parametrize(
    "api_base",
    [
        "not-a-url",
        "ftp://model.example.test/v1",
        "https://user:password@model.example.test/v1",
        "https://model.example.test:invalid/v1",
        "https://model.example.test:0/v1",
        "https://model.example.test/v1?token=unsafe",
        "https://model.example.test/v1#fragment",
    ],
)
def test_invalid_model_api_base_is_rejected_without_echoing_value(api_base: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=api_base,
        model_api_key="fake-test-key",
        model_name="test-model",
        model_timeout_seconds=10,
    )

    with pytest.raises(ModelConfigurationError) as exc_info:
        settings.require_model_provider()

    assert api_base not in str(exc_info.value)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_model_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(
        ValidationError,
        match="MODEL_TIMEOUT_SECONDS must be a finite positive number",
    ):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            model_timeout_seconds=timeout,
        )


def test_settings_repr_masks_model_api_key() -> None:
    secret = "fake-repr-secret"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_key=secret,
    )

    rendered = repr(settings)

    assert secret not in rendered
    assert "**********" in rendered
