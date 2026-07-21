"""Configuration loading and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

import app.config as config_module
from app.config import ModelConfigurationError, Settings, load_settings
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


def test_application_and_health_configuration_do_not_require_model_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        model_api_base=None,
        model_api_key=None,
        model_name=None,
        model_timeout_seconds=None,
    )

    app = create_app(settings)

    assert app.state.settings is settings


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
