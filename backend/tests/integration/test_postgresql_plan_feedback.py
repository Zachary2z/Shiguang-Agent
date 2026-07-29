"""PostgreSQL concurrency and relational-integrity proof for M1-6 feedback."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.application.plan_execution import PlanFeedbackService
from app.domain.collections import (
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    IdempotencyConflictError,
    User,
    UserMode,
)
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_plan_id,
    generate_trace_id,
    generate_user_id,
)
from app.domain.plans import (
    PlanCompletionStatus,
    PlanOperation,
    PlanStatus,
    PlanVersion,
    PlanVersionConflictError,
)
from app.infrastructure.db import Database
from app.infrastructure.db.models import (
    CollectionItemModel,
    CollectionVisitSourceModel,
    PlanFeedbackAuditModel,
    PlanFeedbackStateModel,
    PlanItemModel,
)
from app.infrastructure.repositories import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyPlanRepository,
    plan_request_fingerprint,
)
from tests.contract.test_m1_6_execution import _constraints, _draft


async def _seed_confirmed_plan(
    database: Database,
    *,
    user_id: str | None = None,
) -> tuple[str, str, str, tuple[str, str]]:
    owner = user_id or generate_user_id()
    constraints = _constraints()
    now = constraints.created_at
    collection_id = generate_collection_item_id()
    plan_id = generate_plan_id()
    async with database.session() as session:
        collections = SqlAlchemyCollectionRepository(session)
        if await collections.get_user(user_id=owner) is None:
            await collections.add_user(
                user_id=owner,
                user=User(id=owner, mode=UserMode.DEMO, created_at=now),
            )
        await collections.add_collection_item(
            user_id=owner,
            item=CollectionItem(
                id=collection_id,
                user_id=owner,
                kind=CollectionKind.PLACE,
                title="深圳当代艺术与城市规划馆",
                status=CollectionStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            ),
        )
        plans = SqlAlchemyPlanRepository(session)
        await plans.add(
            PlanVersion(
                id=plan_id,
                root_plan_id=plan_id,
                user_id=owner,
                version=1,
                operation=PlanOperation.GENERATE,
                status=PlanStatus.GENERATING,
                constraints=constraints,
                trace_id=generate_trace_id(),
                idempotency_key=f"seed-{plan_id}",
                created_at=now,
                updated_at=now,
            ),
            request_fingerprint=plan_request_fingerprint("seed"),
        )
        await plans.complete_generation(
            user_id=owner,
            plan_id=plan_id,
            draft=_draft(collection_id),
            now=now,
        )
        await plans.confirm(
            user_id=owner,
            plan_id=plan_id,
            idempotency_key=f"confirm-{plan_id}",
            request_fingerprint=plan_request_fingerprint("confirm"),
            now=now,
        )
        await session.commit()
        item_ids = tuple(
            (
                await session.scalars(
                    select(PlanItemModel.id)
                    .where(PlanItemModel.plan_id == plan_id)
                    .order_by(PlanItemModel.item_index)
                )
            ).all()
        )
    assert len(item_ids) == 2
    return owner, plan_id, collection_id, (item_ids[0], item_ids[1])


async def _submit(
    database: Database,
    *,
    user_id: str,
    plan_id: str,
    item_id: str,
    key: str,
    expected_revision: int | None = None,
    status: PlanCompletionStatus = PlanCompletionStatus.PARTIALLY_COMPLETED,
):
    async with database.session() as session:
        return await PlanFeedbackService().submit(
            session=session,
            user_id=user_id,
            plan_id=plan_id,
            completion_status=status,
            visited_plan_item_ids=(
                (item_id,) if status is PlanCompletionStatus.PARTIALLY_COMPLETED else ()
            ),
            reason=None,
            client_idempotency_key=key,
            expected_revision=expected_revision,
        )


@pytest.mark.postgresql
def test_postgresql_feedback_concurrency_is_idempotent_and_optimistic(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        try:
            user_id, plan_id, collection_id, item_ids = await _seed_confirmed_plan(
                database
            )
            results = await asyncio.gather(
                *(
                    _submit(
                        database,
                        user_id=user_id,
                        plan_id=plan_id,
                        item_id=item_ids[0],
                        key="same-key",
                    )
                    for _ in range(2)
                )
            )
            assert sorted(result.replayed for result in results) == [False, True]
            assert {result.feedback.id for result in results} == {
                results[0].feedback.id
            }
            async with database.session() as session:
                assert await session.scalar(
                    select(func.count()).select_from(PlanFeedbackAuditModel)
                ) == 1
                state = await session.get(PlanFeedbackStateModel, plan_id)
                collection = await session.get(CollectionItemModel, collection_id)
                statuses = tuple(
                    (
                        await session.scalars(
                            select(PlanItemModel.execution_status)
                            .where(PlanItemModel.plan_id == plan_id)
                            .order_by(PlanItemModel.item_index)
                        )
                    ).all()
                )
                assert state is not None and state.revision == 1
                assert collection is not None
                assert (collection.status, collection.version) == ("visited", 2)
                assert statuses == ("visited", "not_visited")
                assert await session.scalar(
                    select(func.count()).select_from(CollectionVisitSourceModel)
                ) == 1

            with pytest.raises(IdempotencyConflictError):
                await _submit(
                    database,
                    user_id=user_id,
                    plan_id=plan_id,
                    item_id=item_ids[0],
                    key="same-key",
                    status=PlanCompletionStatus.NOT_COMPLETED,
                )
            owner, other_plan, _collection, other_items = await _seed_confirmed_plan(
                database,
                user_id=user_id,
            )
            attempts = await asyncio.gather(
                *(
                    _submit(
                        database,
                        user_id=owner,
                        plan_id=other_plan,
                        item_id=other_items[0],
                        key=key,
                    )
                    for key in ("different-a", "different-b")
                ),
                return_exceptions=True,
            )
            assert sum(not isinstance(result, Exception) for result in attempts) == 1
            assert sum(
                isinstance(result, PlanVersionConflictError) for result in attempts
            ) == 1
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_postgresql_failed_feedback_can_retry_same_key(
    postgresql_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        try:
            user_id, plan_id, _collection_id, item_ids = await _seed_confirmed_plan(
                database
            )
            original = PlanFeedbackService._recompute_collections

            async def fail_recompute(**_kwargs) -> None:
                raise RuntimeError("postgres rollback fixture")

            monkeypatch.setattr(
                PlanFeedbackService,
                "_recompute_collections",
                staticmethod(fail_recompute),
            )
            with pytest.raises(RuntimeError, match="rollback fixture"):
                await _submit(
                    database,
                    user_id=user_id,
                    plan_id=plan_id,
                    item_id=item_ids[0],
                    key="retry-after-rollback",
                )
            monkeypatch.setattr(
                PlanFeedbackService,
                "_recompute_collections",
                staticmethod(original),
            )
            retried = await _submit(
                database,
                user_id=user_id,
                plan_id=plan_id,
                item_id=item_ids[0],
                key="retry-after-rollback",
            )
            assert retried.replayed is False
            assert retried.feedback.revision == 1
            async with database.session() as session:
                assert await session.scalar(
                    select(func.count()).select_from(PlanFeedbackAuditModel)
                ) == 1
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_postgresql_feedback_pointers_stay_within_plan_owner(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        try:
            user_id, plan_id, _collection_id, item_ids = await _seed_confirmed_plan(
                database
            )
            first = await _submit(
                database,
                user_id=user_id,
                plan_id=plan_id,
                item_id=item_ids[0],
                key="pointer-first",
            )
            second = await _submit(
                database,
                user_id=user_id,
                plan_id=plan_id,
                item_id=item_ids[0],
                key="pointer-second",
                expected_revision=1,
                status=PlanCompletionStatus.NOT_COMPLETED,
            )
            other_user, other_plan, _other_collection, other_items = (
                await _seed_confirmed_plan(database)
            )
            other = await _submit(
                database,
                user_id=other_user,
                plan_id=other_plan,
                item_id=other_items[0],
                key="pointer-other",
            )
            _owner, same_owner_plan, _same_owner_collection, same_owner_items = (
                await _seed_confirmed_plan(database, user_id=user_id)
            )
            same_owner_other = await _submit(
                database,
                user_id=user_id,
                plan_id=same_owner_plan,
                item_id=same_owner_items[0],
                key="pointer-same-owner-other-plan",
            )

            async with database.session() as session:
                state = await session.get(PlanFeedbackStateModel, plan_id)
                audit = await session.get(PlanFeedbackAuditModel, second.feedback.id)
                assert state is not None and audit is not None
                assert state.current_feedback_id == second.feedback.id
                assert audit.corrects_feedback_id == first.feedback.id

            for pointer in (
                "fdb_ffffffffffffffffffffffffffffffff",
                other.feedback.id,
                same_owner_other.feedback.id,
            ):
                async with database.session() as session:
                    with pytest.raises(IntegrityError):
                        await session.execute(
                            update(PlanFeedbackStateModel)
                            .where(PlanFeedbackStateModel.plan_id == plan_id)
                            .values(current_feedback_id=pointer)
                        )
                        await session.commit()
                    await session.rollback()

                    with pytest.raises(IntegrityError):
                        await session.execute(
                            update(PlanFeedbackAuditModel)
                            .where(PlanFeedbackAuditModel.id == second.feedback.id)
                            .values(corrects_feedback_id=pointer)
                        )
                        await session.commit()
                    await session.rollback()
        finally:
            await database.close()

    asyncio.run(scenario())
