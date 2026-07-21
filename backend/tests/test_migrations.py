"""Alembic round-trip and M0-1C/M0-2A schema constraint tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = "20260721_0003"
PREVIOUS_REVISION = "20260721_0002"
HEAD_TABLES = {
    "agent_runs",
    "alembic_version",
    "collection_items",
    "collection_sources",
    "messages",
    "sessions",
    "sources",
    "tool_runs",
    "users",
}


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


def _insert_user(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        """
        INSERT INTO users (id, mode, city, timezone, created_at)
        VALUES (?, 'real', 'shenzhen', 'Asia/Shanghai', ?)
        """,
        (user_id, "2026-07-21T00:00:00+00:00"),
    )


def _insert_source(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    user_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO sources (
            id, user_id, type, parse_status, metadata_json, created_at, updated_at
        ) VALUES (?, ?, 'text', 'parsed', '{}', ?, ?)
        """,
        (
            source_id,
            user_id,
            "2026-07-21T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
        ),
    )


def _insert_collection_item(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    user_id: str,
    status: str = "active",
    version: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO collection_items (
            id, user_id, kind, title, city, tags_json, status, version,
            created_at, updated_at
        ) VALUES (?, ?, 'place', 'fixture', 'shenzhen', '[]', ?, ?, ?, ?)
        """,
        (
            item_id,
            user_id,
            status,
            version,
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
    assert table_names(database_path) == HEAD_TABLES

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

    with sqlite3.connect(database_path) as connection:
        _insert_agent_run(connection, suffix="preserved")
        connection.commit()

    command.downgrade(alembic_config, PREVIOUS_REVISION)
    assert current_revision(database_path) == PREVIOUS_REVISION
    assert table_names(database_path) == {"agent_runs", "alembic_version", "tool_runs"}
    with sqlite3.connect(database_path) as connection:
        preserved_run = connection.execute(
            "SELECT id, status FROM agent_runs WHERE id LIKE 'arn_preserved%'"
        ).fetchone()
        assert preserved_run is not None and preserved_run[1] == "queued"
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            INSERT INTO tool_runs (
                id, agent_run_id, sequence, tool_call_id, tool_name,
                arguments_fingerprint, input_summary, status, started_at, created_at
            ) VALUES (?, ?, 1, 'call-preserved', 'echo', ?, '{}', 'running', ?, ?)
            """,
            (
                "tlr_dddddddddddddddddddddddddddddddd",
                preserved_run[0],
                "d" * 64,
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
            ),
        )
        connection.commit()
        assert connection.execute(
            "SELECT status FROM agent_runs WHERE id LIKE 'arn_preserved%'"
        ).fetchone() == ("queued",)
        assert connection.execute(
            "SELECT status FROM tool_runs WHERE agent_run_id = ?",
            (preserved_run[0],),
        ).fetchone() == ("running",)

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION
    assert table_names(database_path) == HEAD_TABLES


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


def test_collection_migration_has_exact_fields_named_constraints_and_useful_indexes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "collection-schema.db"
    command.upgrade(_alembic_config(monkeypatch, database_path), "head")

    expected_columns = {
        "users": {"id", "mode", "city", "timezone", "created_at"},
        "sessions": {
            "id",
            "user_id",
            "channel",
            "status",
            "summary",
            "created_at",
            "updated_at",
        },
        "messages": {
            "id",
            "session_id",
            "role",
            "content_type",
            "content",
            "trace_id",
            "created_at",
        },
        "sources": {
            "id",
            "user_id",
            "type",
            "url",
            "file_key",
            "platform",
            "parse_status",
            "fetched_at",
            "metadata_json",
            "created_at",
            "updated_at",
        },
        "collection_items": {
            "id",
            "user_id",
            "kind",
            "title",
            "city",
            "district",
            "address",
            "event_start_at",
            "event_end_at",
            "price_amount",
            "price_currency",
            "tags_json",
            "status",
            "version",
            "created_at",
            "updated_at",
        },
        "collection_sources": {
            "collection_item_id",
            "source_id",
            "user_id",
            "created_at",
        },
    }

    with sqlite3.connect(database_path) as connection:
        for table_name, columns in expected_columns.items():
            assert {
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")
            } == columns

        normal_indexes = {
            table_name: {
                columns
                for unique, columns in index_definitions(connection, table_name).values()
                if not unique
            }
            for table_name in expected_columns
        }
        table_sql = " ".join(
            str(row[0])
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name IN ('users', 'sessions', 'messages', 'sources', "
                "'collection_items', 'collection_sources')"
            )
        )
        collection_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(collection_sources)"
        ).fetchall()

        _insert_user(connection, "usr_11111111111111111111111111111111")
        _insert_collection_item(
            connection,
            item_id="col_11111111111111111111111111111111",
            user_id="usr_11111111111111111111111111111111",
        )
        connection.commit()
        query_plan = " ".join(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM collection_items "
                "WHERE user_id = ? AND status = ? ORDER BY created_at",
                ("usr_11111111111111111111111111111111", "active"),
            )
        )

    assert normal_indexes == {
        "users": set(),
        "sessions": {("user_id", "updated_at")},
        "messages": {("session_id", "created_at")},
        "sources": {("user_id", "parse_status", "created_at")},
        "collection_items": {("user_id", "status", "created_at")},
        "collection_sources": {("source_id",)},
    }
    assert len(collection_foreign_keys) == 4
    assert {row[2] for row in collection_foreign_keys} == {"collection_items", "sources"}
    assert "ix_collection_items_user_status_created" in query_plan
    for constraint_name in (
        "pk_users",
        "pk_sessions",
        "pk_messages",
        "pk_sources",
        "pk_collection_items",
        "pk_collection_sources",
        "fk_sessions_user_id_users",
        "fk_messages_session_id_sessions",
        "fk_sources_user_id_users",
        "fk_collection_items_user_id_users",
        "fk_collection_sources_item_owner_collection_items",
        "fk_collection_sources_source_owner_sources",
        "uq_sources_id_user_id",
        "uq_collection_items_id_user_id",
        "ck_users_mode",
        "ck_sessions_channel",
        "ck_messages_role",
        "ck_sources_type_fields",
        "ck_collection_items_status",
        "ck_collection_items_version_positive",
    ):
        assert constraint_name in table_sql


def test_collection_migration_enforces_checks_foreign_keys_same_owner_and_uniqueness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "collection-constraints.db"
    command.upgrade(_alembic_config(monkeypatch, database_path), "head")
    user_a = "usr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    user_b = "usr_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    source_a = "src_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    source_b = "src_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    item_a = "col_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    item_b = "col_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_user(connection, user_a)
        _insert_user(connection, user_b)
        _insert_source(connection, source_id=source_a, user_id=user_a)
        _insert_source(connection, source_id=source_b, user_id=user_b)
        _insert_collection_item(connection, item_id=item_a, user_id=user_a)
        _insert_collection_item(connection, item_id=item_b, user_id=user_b)
        connection.execute(
            """
            INSERT INTO sessions (
                id, user_id, channel, status, created_at, updated_at
            ) VALUES (?, ?, 'web', 'active', ?, ?)
            """,
            (
                "ses_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                user_a,
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
            ),
        )
        connection.commit()

        invalid_statements = (
            (
                "UPDATE users SET mode = 'admin' WHERE id = ?",
                (user_a,),
            ),
            (
                "UPDATE sessions SET channel = 'email' WHERE user_id = ?",
                (user_a,),
            ),
            (
                """
                INSERT INTO messages (
                    id, session_id, role, content_type, content, created_at
                ) VALUES (?, ?, 'human', 'text', 'fixture', ?)
                """,
                (
                    "msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "ses_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "2026-07-21T00:00:00+00:00",
                ),
            ),
            (
                "UPDATE sources SET parse_status = 'unknown' WHERE id = ?",
                (source_a,),
            ),
            (
                "UPDATE collection_items SET status = 'unknown' WHERE id = ?",
                (item_a,),
            ),
            (
                "UPDATE collection_items SET version = 0 WHERE id = ?",
                (item_a,),
            ),
        )
        for sql, parameters in invalid_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql, parameters)
            connection.rollback()

        connection.execute(
            """
            INSERT INTO collection_sources (
                collection_item_id, source_id, user_id, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (item_a, source_a, user_a, "2026-07-21T00:00:00+00:00"),
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO collection_sources (
                    collection_item_id, source_id, user_id, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (item_a, source_a, user_a, "2026-07-21T00:00:01+00:00"),
            )
        connection.rollback()

        for cross_user_values in (
            (item_a, source_b, user_a),
            (item_b, source_a, user_a),
            (item_a, source_a, user_b),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO collection_sources (
                        collection_item_id, source_id, user_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (*cross_user_values, "2026-07-21T00:00:02+00:00"),
                )
            connection.rollback()

        assert connection.execute(
            "SELECT collection_item_id, source_id, user_id FROM collection_sources"
        ).fetchall() == [(item_a, source_a, user_a)]
