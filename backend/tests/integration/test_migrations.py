"""Alembic round-trip and M0-1C/M0-2 city-contract schema tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEAD_REVISION = "20260724_0007"
PREVIOUS_REVISION = "20260722_0006"
M03D_REVISION = "20260722_0006"
M03D_PREVIOUS_REVISION = "20260721_0005"
M02C_REVISION = "20260721_0005"
M02C_PREVIOUS_REVISION = "20260721_0004"
CITY_REVISION = "20260721_0004"
CITY_PREVIOUS_REVISION = "20260721_0003"
PREVIOUS_TABLES = {
    "agent_runs",
    "alembic_version",
    "collection_items",
    "collection_sources",
    "collection_write_operation_items",
    "collection_write_operations",
    "messages",
    "place_selection_operations",
    "sessions",
    "sources",
    "tool_runs",
    "users",
}
M03D_PREVIOUS_TABLES = PREVIOUS_TABLES - {"place_selection_operations"}
HEAD_TABLES = {
    "agent_runs",
    "alembic_version",
    "collection_items",
    "collection_sources",
    "collection_write_operation_items",
    "collection_write_operations",
    "messages",
    "place_selection_operations",
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


def _exact_target_json(*, poi_id: str, confirmed_at: str) -> str:
    return json.dumps(
        {
            "scope": "exact",
            "poi": {
                "provider": "fixture",
                "poi_id": poi_id,
                "city_code": "0755",
                "coordinate": {
                    "latitude": 22.5,
                    "longitude": 114.0,
                    "coordinate_system": "gcj_02",
                },
            },
            "brand_identity": None,
            "match_status": "matched",
            "confirmed_by": "user_selection",
            "confirmed_at": confirmed_at,
        },
        separators=(",", ":"),
    )


def _any_branch_target_json(*, brand_id: str, confirmed_at: str) -> str:
    return json.dumps(
        {
            "scope": "any_branch",
            "poi": None,
            "brand_identity": {
                "namespace": "curated_brand",
                "stable_id": brand_id,
            },
            "match_status": "ambiguous",
            "confirmed_by": "user_selection",
            "confirmed_at": confirmed_at,
        },
        separators=(",", ":"),
    )


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
        INSERT INTO users (id, mode, default_plan_city, timezone, created_at)
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
    city_hint: str | None = "shenzhen",
) -> None:
    connection.execute(
        """
        INSERT INTO collection_items (
            id, user_id, kind, title, city_hint, tags_json, status, version,
            created_at, updated_at
        ) VALUES (?, ?, 'place', 'fixture', ?, '[]', ?, ?, ?, ?)
        """,
        (
            item_id,
            user_id,
            city_hint,
            status,
            version,
            "2026-07-21T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
        ),
    )


def _insert_0003_user(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        """
        INSERT INTO users (id, mode, city, timezone, created_at)
        VALUES (?, 'real', 'shenzhen', 'Asia/Shanghai', ?)
        """,
        (user_id, "2026-07-21T00:00:00+00:00"),
    )


def _insert_0003_collection_item(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    user_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO collection_items (
            id, user_id, kind, title, city, tags_json, status, version,
            created_at, updated_at
        ) VALUES (?, ?, 'place', 'fixture', 'shenzhen', '[]', 'active', 1, ?, ?)
        """,
        (
            item_id,
            user_id,
            "2026-07-21T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
        ),
    )


def _insert_write_operation(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    user_id: str,
    source_id: str,
    idempotency_key: str,
    undo_token_hash: str,
) -> None:
    connection.execute(
        """
        INSERT INTO collection_write_operations (
            id, user_id, source_id, idempotency_key, request_fingerprint,
            undo_token_hash, undo_expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            user_id,
            source_id,
            idempotency_key,
            "f" * 64,
            undo_token_hash,
            "2026-07-21T00:10:00+00:00",
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
    assert table_names(database_path) == PREVIOUS_TABLES
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


def test_collection_migration_from_previous_revision_accepts_only_final_statuses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "collection-statuses.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_11111111111111111111111111111111"
    persisted_statuses = (
        "active",
        "pending_selection",
        "pending_details",
        "visited",
        "archived",
        "deleted",
    )

    command.upgrade(alembic_config, PREVIOUS_REVISION)
    assert current_revision(database_path) == PREVIOUS_REVISION
    assert table_names(database_path) == PREVIOUS_TABLES

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION
    assert table_names(database_path) == HEAD_TABLES
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_user(connection, user_id)
        for index, status in enumerate(persisted_statuses, start=1):
            _insert_collection_item(
                connection,
                item_id=f"col_{index:032x}",
                user_id=user_id,
                status=status,
            )
        connection.commit()

        assert connection.execute(
            "SELECT status FROM collection_items ORDER BY id"
        ).fetchall() == [(status,) for status in persisted_statuses]
        for index, transient_status in enumerate(("recognizing", "failed"), start=7):
            with pytest.raises(sqlite3.IntegrityError):
                _insert_collection_item(
                    connection,
                    item_id=f"col_{index:032x}",
                    user_id=user_id,
                    status=transient_status,
                )
            connection.rollback()


def test_0003_to_0004_preserves_shenzhen_as_hint_and_supports_any_city_or_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "city-hints-upgrade.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_11111111111111111111111111111111"
    old_item_id = "col_11111111111111111111111111111111"

    command.upgrade(alembic_config, CITY_PREVIOUS_REVISION)
    with sqlite3.connect(database_path) as connection:
        _insert_0003_user(connection, user_id)
        _insert_0003_collection_item(
            connection,
            item_id=old_item_id,
            user_id=user_id,
        )
        connection.commit()

    command.upgrade(alembic_config, CITY_REVISION)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT default_plan_city FROM users WHERE id = ?",
            (user_id,),
        ).fetchone() == ("shenzhen",)
        assert connection.execute(
            "SELECT city_hint FROM collection_items WHERE id = ?",
            (old_item_id,),
        ).fetchone() == ("shenzhen",)
        for index, hint in enumerate((None, "广州", "上海"), start=2):
            _insert_collection_item(
                connection,
                item_id=f"col_{index:032x}",
                user_id=user_id,
                city_hint=hint,
            )
        connection.commit()
        assert dict(
            connection.execute(
                "SELECT id, city_hint FROM collection_items ORDER BY id"
            ).fetchall()
        ) == {
            old_item_id: "shenzhen",
            "col_00000000000000000000000000000002": None,
            "col_00000000000000000000000000000003": "广州",
            "col_00000000000000000000000000000004": "上海",
        }

        for invalid_hint in ("", "   ", "x" * 101):
            with pytest.raises(sqlite3.IntegrityError):
                _insert_collection_item(
                    connection,
                    item_id="col_ffffffffffffffffffffffffffffffff",
                    user_id=user_id,
                    city_hint=invalid_hint,
                )
            connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE users SET default_plan_city = 'guangzhou' WHERE id = ?",
                (user_id,),
            )
        connection.rollback()


def test_0004_compatible_shenzhen_data_downgrades_and_reupgrades_without_loss(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "city-hints-compatible-roundtrip.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_22222222222222222222222222222222"
    item_id = "col_22222222222222222222222222222222"

    command.upgrade(alembic_config, CITY_REVISION)
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(
            connection,
            item_id=item_id,
            user_id=user_id,
            city_hint="shenzhen",
        )
        connection.commit()

    command.downgrade(alembic_config, CITY_PREVIOUS_REVISION)
    assert current_revision(database_path) == CITY_PREVIOUS_REVISION
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT city FROM users WHERE id = ?",
            (user_id,),
        ).fetchone() == ("shenzhen",)
        assert connection.execute(
            "SELECT city FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == ("shenzhen",)

    command.upgrade(alembic_config, CITY_REVISION)
    assert current_revision(database_path) == CITY_REVISION
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT default_plan_city FROM users WHERE id = ?",
            (user_id,),
        ).fetchone() == ("shenzhen",)
        assert connection.execute(
            "SELECT city_hint FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == ("shenzhen",)


@pytest.mark.parametrize("city_hint", [None, "广州", "上海"])
def test_0004_incompatible_downgrade_fails_before_schema_or_data_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    city_hint: str | None,
) -> None:
    database_path = tmp_path / f"city-hints-incompatible-{city_hint or 'null'}.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_33333333333333333333333333333333"
    item_id = "col_33333333333333333333333333333333"

    command.upgrade(alembic_config, CITY_REVISION)
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(
            connection,
            item_id=item_id,
            user_id=user_id,
            city_hint=city_hint,
        )
        connection.commit()
        before_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('users', 'collection_items') ORDER BY name"
        ).fetchall()
        before_rows = connection.execute(
            "SELECT id, city_hint FROM collection_items ORDER BY id"
        ).fetchall()

    with pytest.raises(RuntimeError, match="cannot downgrade"):
        command.downgrade(alembic_config, CITY_PREVIOUS_REVISION)

    assert current_revision(database_path) == CITY_REVISION
    with sqlite3.connect(database_path) as connection:
        after_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('users', 'collection_items') ORDER BY name"
        ).fetchall()
        after_rows = connection.execute(
            "SELECT id, city_hint FROM collection_items ORDER BY id"
        ).fetchall()
    assert after_schema == before_schema
    assert after_rows == before_rows


def test_0005_schema_enforces_idempotency_undo_order_and_user_ownership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "reversible-write-constraints.db"
    command.upgrade(_alembic_config(monkeypatch, database_path), "head")
    first_user = "usr_11111111111111111111111111111111"
    second_user = "usr_22222222222222222222222222222222"
    first_source = "src_11111111111111111111111111111111"
    second_source = "src_22222222222222222222222222222222"
    first_item = "col_11111111111111111111111111111111"
    second_item = "col_22222222222222222222222222222222"
    first_operation = "cwo_11111111111111111111111111111111"
    second_operation = "cwo_22222222222222222222222222222222"

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        item_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(collection_items)")
        }
        operation_indexes = index_definitions(connection, "collection_write_operations")
        association_indexes = index_definitions(
            connection,
            "collection_write_operation_items",
        )
        table_sql = " ".join(
            str(row[0])
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name IN "
                "('collection_write_operations', 'collection_write_operation_items')"
            )
        )
        assert {
            "business_district",
            "landmark",
            "metro_station",
            "event_start_clue",
            "event_end_clue",
            "missing_fields_json",
            "uncertainties_json",
        }.issubset(item_columns)
        assert any(
            unique and columns == ("user_id", "idempotency_key")
            for unique, columns in operation_indexes.values()
        )
        assert any(
            unique and columns == ("user_id", "source_id")
            for unique, columns in operation_indexes.values()
        )
        assert any(
            unique and columns == ("undo_token_hash",)
            for unique, columns in operation_indexes.values()
        )
        assert any(
            unique and columns == ("operation_id", "sequence")
            for unique, columns in association_indexes.values()
        )
        for constraint in (
            "uq_collection_write_operations_user_idempotency",
            "uq_collection_write_operations_user_source",
            "uq_collection_write_operations_undo_hash",
            "fk_collection_write_operations_source_owner_sources",
            "fk_collection_write_operation_items_operation_owner",
            "fk_collection_write_operation_items_item_owner",
            "uq_collection_write_operation_items_operation_sequence",
        ):
            assert constraint in table_sql

        _insert_user(connection, first_user)
        _insert_user(connection, second_user)
        _insert_source(connection, source_id=first_source, user_id=first_user)
        _insert_source(connection, source_id=second_source, user_id=second_user)
        _insert_collection_item(connection, item_id=first_item, user_id=first_user)
        _insert_collection_item(connection, item_id=second_item, user_id=second_user)
        _insert_write_operation(
            connection,
            operation_id=first_operation,
            user_id=first_user,
            source_id=first_source,
            idempotency_key="same-key",
            undo_token_hash="a" * 64,
        )
        _insert_write_operation(
            connection,
            operation_id=second_operation,
            user_id=second_user,
            source_id=second_source,
            idempotency_key="same-key",
            undo_token_hash="b" * 64,
        )
        connection.execute(
            """
            INSERT INTO collection_write_operation_items (
                operation_id, collection_item_id, user_id, sequence, created_at
            ) VALUES (?, ?, ?, 1, ?)
            """,
            (
                first_operation,
                first_item,
                first_user,
                "2026-07-21T00:00:00+00:00",
            ),
        )
        connection.commit()

        for statement, parameters in (
            (
                """
                INSERT INTO collection_write_operations (
                    id, user_id, source_id, idempotency_key, request_fingerprint,
                    undo_token_hash, undo_expires_at, created_at
                ) VALUES (?, ?, ?, 'same-key', ?, ?, ?, ?)
                """,
                (
                    "cwo_33333333333333333333333333333333",
                    first_user,
                    first_source,
                    "f" * 64,
                    "c" * 64,
                    "2026-07-21T00:10:00+00:00",
                    "2026-07-21T00:00:00+00:00",
                ),
            ),
            (
                """
                INSERT INTO collection_write_operation_items (
                    operation_id, collection_item_id, user_id, sequence, created_at
                ) VALUES (?, ?, ?, 2, ?)
                """,
                (
                    first_operation,
                    second_item,
                    first_user,
                    "2026-07-21T00:00:00+00:00",
                ),
            ),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, parameters)
            connection.rollback()


def test_0005_compatible_data_downgrades_to_0004_and_reupgrades_without_loss(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "m02c-compatible-roundtrip.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_55555555555555555555555555555555"
    item_id = "col_55555555555555555555555555555555"
    command.upgrade(alembic_config, M02C_REVISION)
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(
            connection,
            item_id=item_id,
            user_id=user_id,
            city_hint="广州",
        )
        connection.commit()

    command.downgrade(alembic_config, M02C_PREVIOUS_REVISION)
    assert current_revision(database_path) == M02C_PREVIOUS_REVISION
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT id, city_hint, title FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == (item_id, "广州", "fixture")

    command.upgrade(alembic_config, M02C_REVISION)
    assert current_revision(database_path) == M02C_REVISION
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT id, city_hint, business_district, missing_fields_json "
            "FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == (item_id, "广州", None, "[]")


@pytest.mark.parametrize("incompatible_kind", ["operation", "candidate_metadata"])
def test_0005_incompatible_downgrade_fails_before_any_schema_or_data_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    incompatible_kind: str,
) -> None:
    database_path = tmp_path / f"m02c-downgrade-{incompatible_kind}.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_44444444444444444444444444444444"
    source_id = "src_44444444444444444444444444444444"
    item_id = "col_44444444444444444444444444444444"
    command.upgrade(alembic_config, M02C_REVISION)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_user(connection, user_id)
        _insert_source(connection, source_id=source_id, user_id=user_id)
        _insert_collection_item(connection, item_id=item_id, user_id=user_id)
        if incompatible_kind == "operation":
            _insert_write_operation(
                connection,
                operation_id="cwo_44444444444444444444444444444444",
                user_id=user_id,
                source_id=source_id,
                idempotency_key="downgrade",
                undo_token_hash="d" * 64,
            )
        else:
            connection.execute(
                "UPDATE collection_items SET business_district = '中心区', "
                "missing_fields_json = '[\"address\"]' WHERE id = ?",
                (item_id,),
            )
        connection.commit()
        before_schema = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        before_data = connection.execute(
            "SELECT id, business_district, missing_fields_json FROM collection_items"
        ).fetchall()

    with pytest.raises(RuntimeError, match="cannot downgrade"):
        command.downgrade(alembic_config, M02C_PREVIOUS_REVISION)

    assert current_revision(database_path) == M02C_REVISION
    with sqlite3.connect(database_path) as connection:
        after_schema = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        after_data = connection.execute(
            "SELECT id, business_district, missing_fields_json FROM collection_items"
        ).fetchall()
    assert after_schema == before_schema
    assert after_data == before_data


def test_0006_preserves_legacy_collection_and_round_trips_to_0005(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "m03d-legacy-roundtrip.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_66666666666666666666666666666666"
    item_id = "col_66666666666666666666666666666666"
    command.upgrade(alembic_config, M03D_PREVIOUS_REVISION)
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(connection, item_id=item_id, user_id=user_id)
        connection.commit()

    command.upgrade(alembic_config, M03D_REVISION)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT place_scope, place_target_json, candidate_count "
            "FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == (None, None, 0)

    command.downgrade(alembic_config, M03D_PREVIOUS_REVISION)
    assert current_revision(database_path) == M03D_PREVIOUS_REVISION
    assert table_names(database_path) == M03D_PREVIOUS_TABLES
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT id, title, status FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == (item_id, "fixture", "active")

    command.upgrade(alembic_config, M03D_REVISION)
    assert current_revision(database_path) == M03D_REVISION


@pytest.mark.parametrize("incompatible_kind", ["target", "snapshot", "operation"])
def test_0006_incompatible_downgrade_fails_before_schema_or_data_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    incompatible_kind: str,
) -> None:
    database_path = tmp_path / f"m03d-downgrade-{incompatible_kind}.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_77777777777777777777777777777777"
    source_id = "src_77777777777777777777777777777777"
    item_id = "col_77777777777777777777777777777777"
    command.upgrade(alembic_config, M03D_REVISION)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA ignore_check_constraints=ON")
        _insert_user(connection, user_id)
        _insert_source(connection, source_id=source_id, user_id=user_id)
        _insert_collection_item(connection, item_id=item_id, user_id=user_id)
        if incompatible_kind == "target":
            connection.execute(
                "UPDATE collection_items SET place_scope = 'exact', "
                "place_target_json = '{}', poi_provider = 'fixture', poi_id = 'poi-1', "
                "poi_city_code = '0755', poi_latitude = 22.5, poi_longitude = 114.0, "
                "poi_coordinate_system = 'gcj_02', place_match_status = 'matched', "
                "place_confirmed_by = 'user_selection', place_confirmed_at = ? "
                "WHERE id = ?",
                ("2026-07-22T00:00:00+00:00", item_id),
            )
        elif incompatible_kind == "snapshot":
            connection.execute(
                "UPDATE collection_items SET place_candidate_snapshot_json = '{}', "
                "candidate_count = 1, candidates_queried_at = ? WHERE id = ?",
                ("2026-07-22T00:00:00+00:00", item_id),
            )
        else:
            connection.execute(
                "INSERT INTO place_selection_operations ("
                "user_id, idempotency_key, collection_item_id, source_id, "
                "request_fingerprint, result_item_ids_json, created_at"
                ") VALUES (?, 'selection-1', ?, ?, ?, ?, ?)",
                (
                    user_id,
                    item_id,
                    source_id,
                    "a" * 64,
                    f'["{item_id}"]',
                    "2026-07-22T00:00:00+00:00",
                ),
            )
        connection.commit()
        before_schema = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        before_data = connection.execute(
            "SELECT id, place_scope, candidate_count FROM collection_items"
        ).fetchall()

    with pytest.raises(RuntimeError, match="cannot downgrade"):
        command.downgrade(alembic_config, M03D_PREVIOUS_REVISION)

    assert current_revision(database_path) == M03D_REVISION
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall() == before_schema
        assert connection.execute(
            "SELECT id, place_scope, candidate_count FROM collection_items"
        ).fetchall() == before_data


def test_0006_database_rejects_invalid_targets_duplicates_and_cross_user_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "m03d-constraints.db"
    command.upgrade(_alembic_config(monkeypatch, database_path), "head")
    user_a = "usr_88888888888888888888888888888888"
    user_b = "usr_99999999999999999999999999999999"
    source_a = "src_88888888888888888888888888888888"
    source_b = "src_99999999999999999999999999999999"
    item_a = "col_88888888888888888888888888888881"
    item_duplicate = "col_88888888888888888888888888888882"
    item_b = "col_99999999999999999999999999999991"

    exact_update = (
        "UPDATE collection_items SET place_scope = 'exact', place_target_json = ?, "
        "poi_provider = 'fixture', poi_id = 'shared-poi', poi_city_code = '0755', "
        "poi_latitude = 22.5, poi_longitude = 114.0, "
        "poi_coordinate_system = 'gcj_02', place_match_status = 'matched', "
        "place_confirmed_by = 'user_selection', place_confirmed_at = ? WHERE id = ?"
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_user(connection, user_a)
        _insert_user(connection, user_b)
        _insert_source(connection, source_id=source_a, user_id=user_a)
        _insert_source(connection, source_id=source_b, user_id=user_b)
        _insert_collection_item(connection, item_id=item_a, user_id=user_a)
        _insert_collection_item(connection, item_id=item_duplicate, user_id=user_a)
        _insert_collection_item(connection, item_id=item_b, user_id=user_b)
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE collection_items SET place_scope = 'exact', "
                "place_target_json = '{}', poi_provider = 'fixture', poi_id = 'bad', "
                "poi_latitude = 22.5, poi_longitude = 114.0, "
                "poi_coordinate_system = 'gcj_02', place_match_status = 'matched', "
                "place_confirmed_by = 'user_selection', place_confirmed_at = ? "
                "WHERE id = ?",
                ("2026-07-22T00:00:00+00:00", item_a),
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE collection_items SET place_candidate_snapshot_json = '{}', "
                "candidate_count = 4, candidates_queried_at = ? WHERE id = ?",
                ("2026-07-22T00:00:00+00:00", item_a),
            )
        connection.rollback()

        confirmed_at = "2026-07-22T00:00:00+00:00"
        target_json = _exact_target_json(poi_id="shared-poi", confirmed_at=confirmed_at)
        connection.execute(exact_update, (target_json, confirmed_at, item_a))
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(exact_update, (target_json, confirmed_at, item_duplicate))
        connection.rollback()

        connection.execute(exact_update, (target_json, confirmed_at, item_b))
        connection.commit()
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE poi_id = 'shared-poi'"
        ).fetchone() == (2,)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO place_selection_operations ("
                "user_id, idempotency_key, collection_item_id, source_id, "
                "request_fingerprint, result_item_ids_json, created_at"
                ") VALUES (?, 'cross-owner', ?, ?, ?, ?, ?)",
                (
                    user_a,
                    item_a,
                    source_b,
                    "b" * 64,
                    f'["{item_a}"]',
                    confirmed_at,
                ),
            )


def test_0006_database_protects_json_and_flat_place_consistency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "m03d-json-consistency.db"
    command.upgrade(_alembic_config(monkeypatch, database_path), "head")
    user_id = "usr_12121212121212121212121212121212"
    exact_id = "col_12121212121212121212121212121211"
    brand_item_id = "col_12121212121212121212121212121212"
    confirmed_at = "2026-07-22T00:00:00+00:00"
    queried_at = "2026-07-22T00:01:00+00:00"
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(connection, item_id=exact_id, user_id=user_id)
        _insert_collection_item(connection, item_id=brand_item_id, user_id=user_id)
        connection.execute(
            "UPDATE collection_items SET place_scope = 'exact', place_target_json = ?, "
            "poi_provider = 'fixture', poi_id = 'poi-exact', poi_city_code = '0755', "
            "poi_latitude = 22.5, poi_longitude = 114.0, "
            "poi_coordinate_system = 'gcj_02', place_match_status = 'matched', "
            "place_confirmed_by = 'user_selection', place_confirmed_at = ? WHERE id = ?",
            (
                _exact_target_json(poi_id="poi-exact", confirmed_at=confirmed_at),
                confirmed_at,
                exact_id,
            ),
        )
        connection.execute(
            "UPDATE collection_items SET place_scope = 'any_branch', place_target_json = ?, "
            "brand_namespace = 'curated_brand', brand_id = 'brand-exact', "
            "place_match_status = 'ambiguous', place_confirmed_by = 'user_selection', "
            "place_confirmed_at = ? WHERE id = ?",
            (
                _any_branch_target_json(
                    brand_id="brand-exact",
                    confirmed_at=confirmed_at,
                ),
                confirmed_at,
                brand_item_id,
            ),
        )
        snapshot_json = json.dumps(
            {
                "result": {"candidates": [{"poi_id": "one"}, {"poi_id": "two"}]},
                "queried_at": queried_at,
            },
            separators=(",", ":"),
        )
        connection.execute(
            "UPDATE collection_items SET place_candidate_snapshot_json = ?, "
            "candidate_count = 2, candidates_queried_at = ? WHERE id = ?",
            (snapshot_json, queried_at, exact_id),
        )
        connection.commit()

        for statement in (
            "UPDATE collection_items SET poi_id = 'forged' WHERE id = ?",
            "UPDATE collection_items SET poi_latitude = 1.0 WHERE id = ?",
            "UPDATE collection_items SET place_confirmed_by = 'auto_unique_match' WHERE id = ?",
            "UPDATE collection_items SET candidate_count = 1 WHERE id = ?",
            "UPDATE collection_items SET candidates_queried_at = "
            "'2026-07-22T00:02:00+00:00' WHERE id = ?",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, (exact_id,))
            connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE collection_items SET brand_id = 'forged' WHERE id = ?",
                (brand_item_id,),
            )
        connection.rollback()

        table_sql = str(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'collection_items'"
            ).fetchone()[0]
        )
    assert "ck_collection_items_place_target_json_consistency" in table_sql
    assert "ck_collection_items_candidate_snapshot_json_consistency" in table_sql


def test_0007_upgrades_legacy_rows_with_null_dates_and_round_trips_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "event-date-roundtrip.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_24242424242424242424242424242424"
    item_id = "col_24242424242424242424242424242424"
    command.upgrade(alembic_config, PREVIOUS_REVISION)
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(connection, item_id=item_id, user_id=user_id)
        connection.commit()

    command.upgrade(alembic_config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT event_start_date, event_end_date FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == (None, None)
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(collection_items)")
        }
    assert {"event_start_date", "event_end_date"} <= columns

    command.downgrade(alembic_config, PREVIOUS_REVISION)
    assert current_revision(database_path) == PREVIOUS_REVISION
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(collection_items)")
        }
        assert "event_start_date" not in columns
        assert connection.execute(
            "SELECT id, title FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == (item_id, "fixture")

    command.upgrade(alembic_config, "head")
    assert current_revision(database_path) == HEAD_REVISION


def test_0007_enforces_inclusive_date_order_and_refuses_lossy_downgrade(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "event-date-constraints.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    user_id = "usr_25252525252525252525252525252525"
    item_id = "col_25252525252525252525252525252525"
    command.upgrade(alembic_config, "head")
    with sqlite3.connect(database_path) as connection:
        _insert_user(connection, user_id)
        _insert_collection_item(connection, item_id=item_id, user_id=user_id)
        connection.execute(
            "UPDATE collection_items SET kind = 'event', event_start_date = ?, "
            "event_end_date = ? WHERE id = ?",
            ("2026-06-13", "2026-07-31", item_id),
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE collection_items SET event_end_date = ? WHERE id = ?",
                ("2026-06-12", item_id),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE collection_items SET kind = 'place' WHERE id = ?",
                (item_id,),
            )
        connection.rollback()

    with pytest.raises(RuntimeError, match="Event date facts exist"):
        command.downgrade(alembic_config, PREVIOUS_REVISION)
    assert current_revision(database_path) == HEAD_REVISION
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT event_start_date, event_end_date FROM collection_items WHERE id = ?",
            (item_id,),
        ).fetchone() == ("2026-06-13", "2026-07-31")


def test_alembic_has_one_head_and_metadata_matches_head_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "alembic-check.db"
    alembic_config = _alembic_config(monkeypatch, database_path)
    script = ScriptDirectory.from_config(alembic_config)

    assert script.get_heads() == [HEAD_REVISION]
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)


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
        "users": {"id", "mode", "default_plan_city", "timezone", "created_at"},
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
            "city_hint",
            "district",
            "address",
            "business_district",
            "landmark",
            "metro_station",
            "event_start_date",
            "event_end_date",
            "event_start_at",
            "event_end_at",
            "event_start_clue",
            "event_end_clue",
            "price_amount",
            "price_currency",
            "tags_json",
            "missing_fields_json",
            "uncertainties_json",
            "place_scope",
            "place_target_json",
            "poi_provider",
            "poi_id",
            "poi_city_code",
            "poi_latitude",
            "poi_longitude",
            "poi_coordinate_system",
            "brand_namespace",
            "brand_id",
            "place_match_status",
            "place_confirmed_by",
            "place_confirmed_at",
            "place_candidate_snapshot_json",
            "candidate_count",
            "candidates_queried_at",
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
        "ck_users_default_plan_city",
        "ck_sessions_channel",
        "ck_messages_role",
        "ck_sources_type_fields",
        "ck_collection_items_status",
        "ck_collection_items_city_hint",
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
        connection.execute(
            """
            INSERT INTO sessions (
                id, user_id, channel, status, created_at, updated_at
            ) VALUES (?, ?, 'demo', 'active', ?, ?)
            """,
            (
                "ses_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                user_b,
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, session_id, role, content_type, content, created_at
            ) VALUES (?, ?, 'assistant', 'text', 'safe summary', ?)
            """,
            (
                "msg_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "ses_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
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
                "UPDATE sessions SET channel = 'wechat' WHERE user_id = ?",
                (user_a,),
            ),
            (
                "UPDATE sessions SET channel = 'clawbot' WHERE user_id = ?",
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
                """
                INSERT INTO messages (
                    id, session_id, role, content_type, content, created_at
                ) VALUES (?, ?, 'system', 'text', 'private-system-prompt', ?)
                """,
                (
                    "msg_cccccccccccccccccccccccccccccccc",
                    "ses_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "2026-07-21T00:00:00+00:00",
                ),
            ),
            (
                """
                INSERT INTO messages (
                    id, session_id, role, content_type, content, created_at
                ) VALUES (?, ?, 'tool', 'text', 'private-tool-payload', ?)
                """,
                (
                    "msg_dddddddddddddddddddddddddddddddd",
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
                "UPDATE collection_items SET status = 'recognizing' WHERE id = ?",
                (item_a,),
            ),
            (
                "UPDATE collection_items SET status = 'failed' WHERE id = ?",
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

        assert connection.execute(
            "SELECT channel FROM sessions ORDER BY channel"
        ).fetchall() == [("demo",), ("web",)]
        assert connection.execute(
            "SELECT role, content FROM messages"
        ).fetchall() == [("assistant", "safe summary")]
        assert connection.execute(
            "SELECT status FROM collection_items ORDER BY id"
        ).fetchall() == [("active",), ("active",)]

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
