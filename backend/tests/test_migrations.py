"""Alembic upgrade and downgrade round-trip tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = "20260721_0001"


def current_revision(database_path: Path) -> str | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    return {str(row[0]) for row in rows}


def test_alembic_upgrade_downgrade_upgrade_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION
    assert table_names(database_path) == {"alembic_version"}

    command.downgrade(alembic_config, "base")
    assert current_revision(database_path) is None

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION
    assert table_names(database_path) == {"alembic_version"}
