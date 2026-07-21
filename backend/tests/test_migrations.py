"""Alembic round-trip and M0-1C schema constraint tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = "20260721_0002"
PREVIOUS_REVISION = "20260721_0001"


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


def index_definitions(
    connection: sqlite3.Connection,
    table_name: str,
) -> dict[str, tuple[bool, tuple[str, ...]]]:
    definitions: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for row in connection.execute(f'PRAGMA index_list("{table_name}")'):
        index_name = str(row[1])
        columns = tuple(
            str(column[2])
            for column in connection.execute(f'PRAGMA index_info("{index_name}")')
        )
        definitions[index_name] = (bool(row[2]), columns)
    return definitions


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_path: Path) -> Config:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _insert_agent_run(connection: sqlite3.Connection, *, suffix: str = "one") -> None:
    connection.execute(
        """
        INSERT INTO agent_runs (
            id, trace_id, intent, workflow, status, model_names_json,
            model_calls_json, cost_estimation_source, cost_unknown_reason,
            created_at, updated_at
        ) VALUES (
            ?, ?, 'test', 'test', 'queued', '[]', '[]',
            'not_evaluated', 'not_evaluated', ?, ?
        )
        """,
        (
            f"arn_{suffix:0<32}"[:36],
            f"trc_{suffix:0<32}"[:36],
            "2026-07-21T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
        ),
    )


def test_alembic_upgrade_downgrade_upgrade_round_trip_and_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration.db"
    alembic_config = _alembic_config(monkeypatch, database_path)

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION
    assert table_names(database_path) == {"agent_runs", "alembic_version", "tool_runs"}

    with sqlite3.connect(database_path) as connection:
        agent_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(agent_runs)")
        }
        tool_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(tool_runs)")
        }
        agent_indexes = index_definitions(connection, "agent_runs")
        tool_indexes = index_definitions(connection, "tool_runs")
        foreign_keys = connection.execute("PRAGMA foreign_key_list(tool_runs)").fetchall()
        table_sql = " ".join(
            str(row[0])
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name IN ('agent_runs', 'tool_runs')"
            )
        )

    assert {
        "id",
        "trace_id",
        "user_id",
        "session_id",
        "intent",
        "workflow",
        "status",
        "model_names_json",
        "model_calls_json",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "estimated_cost",
        "cost_currency",
        "cost_estimation_source",
        "cost_unknown_reason",
        "duration_ms",
        "error_code",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    } == agent_columns
    assert {
        "id",
        "agent_run_id",
        "sequence",
        "tool_call_id",
        "tool_name",
        "arguments_fingerprint",
        "input_summary",
        "status",
        "output_summary",
        "latency_ms",
        "error_code",
        "started_at",
        "finished_at",
        "created_at",
    } == tool_columns
    assert "ix_agent_runs_trace_id" not in agent_indexes
    assert "ix_tool_runs_agent_run_id" not in tool_indexes
    assert any(
        unique and columns == ("trace_id",)
        for unique, columns in agent_indexes.values()
    )
    assert any(
        unique and columns == ("agent_run_id", "sequence")
        for unique, columns in tool_indexes.values()
    )
    assert all(unique for unique, _columns in agent_indexes.values())
    assert all(unique for unique, _columns in tool_indexes.values())
    assert "uq_agent_runs_trace_id" in table_sql
    assert "uq_tool_runs_run_sequence" in table_sql
    assert len(foreign_keys) == 1
    assert foreign_keys[0][2] == "agent_runs"
    assert foreign_keys[0][3:5] == ("agent_run_id", "id")
    for constraint_name in (
        "ck_agent_runs_status",
        "ck_agent_runs_input_tokens_nonnegative",
        "ck_agent_runs_duration_bound",
        "ck_tool_runs_status",
        "ck_tool_runs_sequence_positive",
        "ck_tool_runs_latency_nonnegative",
    ):
        assert constraint_name in table_sql

    command.downgrade(alembic_config, PREVIOUS_REVISION)
    assert current_revision(database_path) == PREVIOUS_REVISION
    assert table_names(database_path) == {"alembic_version"}

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION
    assert table_names(database_path) == {"agent_runs", "alembic_version", "tool_runs"}


def test_migration_enforces_unique_foreign_key_and_check_constraints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "constraints.db"
    command.upgrade(_alembic_config(monkeypatch, database_path), "head")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_agent_run(connection)
        connection.commit()

        run_id, trace_id = connection.execute(
            "SELECT id, trace_id FROM agent_runs"
        ).fetchone()
        assert connection.execute(
            "SELECT id FROM agent_runs WHERE trace_id = ?",
            (trace_id,),
        ).fetchone() == (run_id,)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id, trace_id, intent, workflow, status, model_names_json,
                    model_calls_json, cost_estimation_source, cost_unknown_reason,
                    created_at, updated_at
                ) SELECT 'arn_duplicate', trace_id, intent, workflow, status,
                    model_names_json, model_calls_json, cost_estimation_source,
                    cost_unknown_reason, created_at, updated_at FROM agent_runs LIMIT 1
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE agent_runs SET input_tokens = -1 WHERE id LIKE 'arn_%'"
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO tool_runs (
                    id, agent_run_id, sequence, tool_call_id, tool_name,
                    arguments_fingerprint, input_summary, status,
                    started_at, created_at
                ) VALUES (
                    'tlr_missing', 'arn_missing', 1, 'call-1', 'echo',
                    ?, '{}', 'running', ?, ?
                )
                """,
                (
                    "a" * 64,
                    "2026-07-21T00:00:00+00:00",
                    "2026-07-21T00:00:00+00:00",
                ),
            )
        connection.rollback()

        tool_values = (
            "tlr_one",
            run_id,
            1,
            "call-1",
            "echo",
            "b" * 64,
            "{}",
            "succeeded",
            0,
            "2026-07-21T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
        )
        connection.execute(
            """
            INSERT INTO tool_runs (
                id, agent_run_id, sequence, tool_call_id, tool_name,
                arguments_fingerprint, input_summary, status, latency_ms,
                started_at, finished_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tool_values,
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO tool_runs (
                    id, agent_run_id, sequence, tool_call_id, tool_name,
                    arguments_fingerprint, input_summary, status, latency_ms,
                    started_at, finished_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("tlr_two", *tool_values[1:]),
            )
        connection.rollback()

        connection.execute(
            """
            INSERT INTO tool_runs (
                id, agent_run_id, sequence, tool_call_id, tool_name,
                arguments_fingerprint, input_summary, status, latency_ms,
                started_at, finished_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tlr_two",
                run_id,
                2,
                "call-2",
                "echo",
                "c" * 64,
                "{}",
                "succeeded",
                0,
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
            ),
        )
        connection.commit()

        assert connection.execute(
            "SELECT id FROM tool_runs WHERE agent_run_id = ? AND sequence = ?",
            (run_id, 2),
        ).fetchone() == ("tlr_two",)
        assert connection.execute(
            "SELECT sequence FROM tool_runs WHERE agent_run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall() == [(1,), (2,)]
