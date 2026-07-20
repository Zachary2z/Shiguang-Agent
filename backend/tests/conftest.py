"""Test process configuration that explicitly disables developer dotenv loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import Settings

os.environ["APP_ENV"] = "test"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "app.db"
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{database_path}",
        log_level="DEBUG",
    )
