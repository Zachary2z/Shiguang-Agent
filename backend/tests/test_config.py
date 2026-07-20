"""Configuration loading and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import app.config as config_module
from app.config import Settings, load_settings


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
