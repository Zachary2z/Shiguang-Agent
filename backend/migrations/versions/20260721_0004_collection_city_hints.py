"""Decouple collection city hints from the Shenzhen planning city.

Revision ID: 20260721_0004
Revises: 20260721_0003
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0004"
down_revision: str | Sequence[str] | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CITY_HINT_CHECK = (
    "city_hint IS NULL OR "
    "(city_hint = trim(city_hint) AND length(city_hint) BETWEEN 1 AND 100)"
)


def upgrade() -> None:
    """Rename the planning default and make collection city text an optional hint."""

    with op.batch_alter_table("users", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_users_city", type_="check")
        batch_op.alter_column(
            "city",
            new_column_name="default_plan_city",
            existing_type=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_users_default_plan_city",
            "default_plan_city IN ('shenzhen')",
        )

    with op.batch_alter_table("collection_items", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_collection_items_city", type_="check")
        batch_op.alter_column(
            "city",
            new_column_name="city_hint",
            existing_type=sa.String(length=32),
            type_=sa.String(length=100),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.create_check_constraint(
            "ck_collection_items_city_hint",
            _CITY_HINT_CHECK,
        )


def downgrade() -> None:
    """Restore 0003 only when every city hint can be represented without coercion."""

    connection = op.get_bind()
    incompatible_count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM collection_items "
            "WHERE city_hint IS NULL OR city_hint <> 'shenzhen'"
        )
    )
    if incompatible_count:
        raise RuntimeError(
            "cannot downgrade to 20260721_0003 while collection city hints are "
            "NULL or differ from 'shenzhen'"
        )

    with op.batch_alter_table("collection_items", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_collection_items_city_hint", type_="check")
        batch_op.alter_column(
            "city_hint",
            new_column_name="city",
            existing_type=sa.String(length=100),
            type_=sa.String(length=32),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_collection_items_city",
            "city IN ('shenzhen')",
        )

    with op.batch_alter_table("users", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_users_default_plan_city", type_="check")
        batch_op.alter_column(
            "default_plan_city",
            new_column_name="city",
            existing_type=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_users_city",
            "city IN ('shenzhen')",
        )
