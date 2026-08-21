from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.epistemic_rollout_repository import (
    EpistemicRolloutIdentity,
    PostgresEpistemicRolloutRepository,
)

DATABASE_URL = os.getenv("OPEX_DATABASE_URL")
MIGRATION_DATABASE_URL = os.getenv("OPEX_MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not MIGRATION_DATABASE_URL,
    reason="PostgreSQL acceptance environment is not configured",
)

TENANT_A = UUID("00000000-0000-4000-8000-0000000000a1")
TENANT_B = UUID("00000000-0000-4000-8000-0000000000b1")
NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)
CANDIDATE = "a" * 64
BASELINE = "b" * 64
BASELINE_PROFILE = "c" * 64
ACTIVATION = "d" * 64
SNAPSHOT_ACTIVE = "e" * 64
SNAPSHOT_ROLLED_BACK = "f" * 64


def _driver_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
async def seed_tenants() -> None:
    if not MIGRATION_DATABASE_URL:
        return
    connection = await asyncpg.connect(_driver_url(MIGRATION_DATABASE_URL))
    try:
        for tenant_id, slug in ((TENANT_A, "jarvis-a"), (TENANT_B, "jarvis-b")):
            await connection.execute(
                """
                INSERT INTO tenants (id, slug, display_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (id) DO NOTHING
                """,
                tenant_id,
                slug,
                f"Jarvis {slug}",
            )
    finally:
        await connection.close()


@asynccontextmanager
async def runtime_session(tenant_id: UUID):
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            yield session
    finally:
        await engine.dispose()


def identity(rollout_id: str, tenant_id: UUID = TENANT_A) -> EpistemicRolloutIdentity:
    return EpistemicRolloutIdentity(
        tenant_id=tenant_id,
        company_id="company-a",
        problem_class="operations-root-cause",
        rollout_id=rollout_id,
    )


def snapshot_payload(
    item: EpistemicRolloutIdentity,
    *,
    generation: int,
    state: str,
    snapshot_fingerprint: str,
) -> dict[str, object]:
    return {
        "identity": {
            "tenant_id": str(item.tenant_id),
            "company_id": item.company_id,
            "problem_class": item.problem_class,
            "rollout_id": item.rollout_id,
        },
        "generation": generation,
        "state": state,
        "snapshot_fingerprint": snapshot_fingerprint,
    }


def activation_payload(item: EpistemicRolloutIdentity) -> dict[str, object]:
    return {
        "identity": {
            "tenant_id": str(item.tenant_id),
            "company_id": item.company_id,
            "problem_class": item.problem_class,
            "rollout_id": item.rollout_id,
        },
        "generation": 1,
        "activation_fingerprint": ACTIVATION,
    }


def receipt_payload(
    item: EpistemicRolloutIdentity,
    *,
    generation: int,
    fingerprint_field: str,
    fingerprint: str,
) -> dict[str, object]:
    return {
        "identity": {
            "tenant_id": str(item.tenant_id),
            "company_id": item.company_id,
            "problem_class": item.problem_class,
            "rollout_id": item.rollout_id,
        },
        "generation": generation,
        fingerprint_field: fingerprint,
    }


async def activate(
    session: AsyncSession,
    item: EpistemicRolloutIdentity,
) -> PostgresEpistemicRolloutRepository:
    repository = PostgresEpistemicRolloutRepository(session)
    rollout, receipt, created = await repository.activate(
        identity=item,
        generation=1,
        candidate_fingerprint=CANDIDATE,
        baseline_fingerprint=BASELINE,
        baseline_profile_fingerprint=BASELINE_PROFILE,
        activation_fingerprint=ACTIVATION,
        snapshot_fingerprint=SNAPSHOT_ACTIVE,
        snapshot_payload=snapshot_payload(
            item, generation=1, state="active", snapshot_fingerprint=SNAPSHOT_ACTIVE
        ),
        receipt_payload=activation_payload(item),
        occurred_at=NOW,
    )
    assert created is True
    assert rollout.version == 1
    assert receipt.sequence == 1
    return repository


def test_migration_is_force_rls_append_only_and_generation_fenced() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/0052_jarvis_epistemic_rollout_authority.py"
    ).read_text()
    assert "jarvis_epistemic_rollouts" in migration
    assert "jarvis_epistemic_rollout_receipts" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "REVOKE UPDATE ON TABLE jarvis_epistemic_rollout_receipts" in migration
    assert "REVOKE DELETE ON TABLE jarvis_epistemic_rollout_receipts" in migration
    assert "generation bigint NOT NULL" in migration
    assert "version bigint NOT NULL DEFAULT 0" in migration
    assert "last_event_hash char(64)" in migration


@pytest.mark.asyncio
async def test_state_health_and_promotion_receipts_survive_restart() -> None:
    item = identity("restart-persistence")
    async with runtime_session(TENANT_A) as session:
        repository = await activate(session, item)
        rollout, _, _ = await repository.append_receipt(
            identity=item,
            generation=1,
            expected_version=1,
            receipt_type="health_observation",
            receipt_fingerprint="1" * 64,
            receipt_payload=receipt_payload(
                item,
                generation=1,
                fingerprint_field="observation_fingerprint",
                fingerprint="1" * 64,
            ),
            occurred_at=NOW + timedelta(minutes=5),
        )
        rollout, _, _ = await repository.append_receipt(
            identity=item,
            generation=1,
            expected_version=rollout.version,
            receipt_type="health_verdict",
            receipt_fingerprint="2" * 64,
            receipt_payload=receipt_payload(
                item,
                generation=1,
                fingerprint_field="verdict_fingerprint",
                fingerprint="2" * 64,
            ),
            occurred_at=NOW + timedelta(minutes=6),
        )
        promotion_specs = (
            ("promotion_evidence", "evidence_fingerprint", "3" * 64),
            ("promotion_approval", "approval_fingerprint", "4" * 64),
            ("promotion_review", "receipt_fingerprint", "5" * 64),
        )
        for receipt_type, field, fingerprint in promotion_specs:
            rollout, _, _ = await repository.append_receipt(
                identity=item,
                generation=1,
                expected_version=rollout.version,
                receipt_type=receipt_type,
                receipt_fingerprint=fingerprint,
                receipt_payload=receipt_payload(
                    item,
                    generation=1,
                    fingerprint_field=field,
                    fingerprint=fingerprint,
                ),
                occurred_at=NOW + timedelta(minutes=10 + rollout.version),
            )

    async with runtime_session(TENANT_A) as restarted_session:
        restarted = PostgresEpistemicRolloutRepository(restarted_session)
        rollout = await restarted.get(identity=item)
        assert rollout is not None
        assert rollout.state == "active"
        assert rollout.version == 6
        assert rollout.last_sequence == 6
        assert rollout.verified_snapshot_payload()["state"] == "active"
        assert len(await restarted.health_history(identity=item, generation=1)) == 2
        assert len(await restarted.promotion_history(identity=item, generation=1)) == 3
        history = await restarted.list_receipts(identity=item)
        assert [receipt.receipt_type for receipt in history] == [
            "activation",
            "health_observation",
            "health_verdict",
            "promotion_evidence",
            "promotion_approval",
            "promotion_review",
        ]
        assert all(receipt.verified_payload() for receipt in history)
        assert await restarted.verify_journal(identity=item) is True


@pytest.mark.asyncio
async def test_compare_and_swap_rejects_stale_writer_and_exact_replay_is_idempotent() -> None:
    item = identity("cas-fencing")
    async with runtime_session(TENANT_A) as session:
        repository = await activate(session, item)
        payload = receipt_payload(
            item,
            generation=1,
            fingerprint_field="observation_fingerprint",
            fingerprint="6" * 64,
        )
        rollout, _, created = await repository.append_receipt(
            identity=item,
            generation=1,
            expected_version=1,
            receipt_type="health_observation",
            receipt_fingerprint="6" * 64,
            receipt_payload=payload,
            occurred_at=NOW + timedelta(minutes=1),
        )
        assert created is True
        assert rollout.version == 2

        replayed, _, created = await repository.append_receipt(
            identity=item,
            generation=1,
            expected_version=1,
            receipt_type="health_observation",
            receipt_fingerprint="6" * 64,
            receipt_payload=payload,
            occurred_at=NOW + timedelta(minutes=1),
        )
        assert created is False
        assert replayed.version == 2

        with pytest.raises(ValueError, match="version_conflict"):
            await repository.append_receipt(
                identity=item,
                generation=1,
                expected_version=1,
                receipt_type="health_verdict",
                receipt_fingerprint="7" * 64,
                receipt_payload=receipt_payload(
                    item,
                    generation=1,
                    fingerprint_field="verdict_fingerprint",
                    fingerprint="7" * 64,
                ),
                occurred_at=NOW + timedelta(minutes=2),
            )
        assert len(await repository.list_receipts(identity=item)) == 2


@pytest.mark.asyncio
async def test_rollback_is_generation_fenced_idempotent_and_restart_safe() -> None:
    item = identity("rollback-persistence")
    rollback_fingerprint = "8" * 64
    rollback_payload = {
        "identity": {
            "tenant_id": str(item.tenant_id),
            "company_id": item.company_id,
            "problem_class": item.problem_class,
            "rollout_id": item.rollout_id,
        },
        "source_generation": 1,
        "resulting_generation": 2,
        "rollback_fingerprint": rollback_fingerprint,
    }
    async with runtime_session(TENANT_A) as session:
        repository = await activate(session, item)
        rollout, _, changed = await repository.apply_rollback(
            identity=item,
            source_generation=1,
            resulting_generation=2,
            expected_version=1,
            activation_fingerprint=ACTIVATION,
            baseline_fingerprint=BASELINE,
            baseline_profile_fingerprint=BASELINE_PROFILE,
            rollback_fingerprint=rollback_fingerprint,
            snapshot_fingerprint=SNAPSHOT_ROLLED_BACK,
            snapshot_payload=snapshot_payload(
                item,
                generation=2,
                state="rolled_back",
                snapshot_fingerprint=SNAPSHOT_ROLLED_BACK,
            ),
            idempotency_key="rollback-on-health-regression",
            receipt_payload=rollback_payload,
            occurred_at=NOW + timedelta(minutes=7),
        )
        assert changed is True
        assert rollout.state == "rolled_back"
        assert rollout.generation == 2
        assert rollout.version == 2
        assert rollout.selected_profile_fingerprint == BASELINE_PROFILE

        replayed, _, changed = await repository.apply_rollback(
            identity=item,
            source_generation=1,
            resulting_generation=2,
            expected_version=1,
            activation_fingerprint=ACTIVATION,
            baseline_fingerprint=BASELINE,
            baseline_profile_fingerprint=BASELINE_PROFILE,
            rollback_fingerprint=rollback_fingerprint,
            snapshot_fingerprint=SNAPSHOT_ROLLED_BACK,
            snapshot_payload=snapshot_payload(
                item,
                generation=2,
                state="rolled_back",
                snapshot_fingerprint=SNAPSHOT_ROLLED_BACK,
            ),
            idempotency_key="rollback-on-health-regression",
            receipt_payload=rollback_payload,
            occurred_at=NOW + timedelta(minutes=7),
        )
        assert changed is False
        assert replayed.generation == 2
        assert len(await repository.list_receipts(identity=item)) == 2

    async with runtime_session(TENANT_A) as restarted_session:
        restarted = PostgresEpistemicRolloutRepository(restarted_session)
        rollout = await restarted.get(identity=item)
        assert rollout is not None
        assert rollout.state == "rolled_back"
        assert rollout.generation == 2
        assert await restarted.verify_journal(identity=item) is True
        with pytest.raises(ValueError, match="not_active"):
            await restarted.append_receipt(
                identity=item,
                generation=1,
                expected_version=rollout.version,
                receipt_type="health_verdict",
                receipt_fingerprint="9" * 64,
                receipt_payload=receipt_payload(
                    item,
                    generation=1,
                    fingerprint_field="verdict_fingerprint",
                    fingerprint="9" * 64,
                ),
                occurred_at=NOW + timedelta(minutes=8),
            )


@pytest.mark.asyncio
async def test_cross_tenant_rls_hides_rollout_even_with_foreign_identity() -> None:
    item = identity("tenant-isolation")
    async with runtime_session(TENANT_A) as session:
        await activate(session, item)

    async with runtime_session(TENANT_B) as session:
        repository = PostgresEpistemicRolloutRepository(session)
        assert await repository.get(identity=item) is None
        assert await repository.list_receipts(identity=item) == ()


@pytest.mark.asyncio
async def test_runtime_cannot_update_or_delete_append_only_receipt_journal() -> None:
    item = identity("append-only-journal")
    async with runtime_session(TENANT_A) as session:
        await activate(session, item)

    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        session = maker()
        try:
            await session.begin()
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(TENANT_A)},
            )
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(
                    text(
                        """
                        UPDATE jarvis_epistemic_rollout_receipts
                        SET payload_json = '{}'
                        WHERE tenant_id = :tenant_id
                          AND company_id = :company_id
                          AND problem_class = :problem_class
                          AND rollout_id = :rollout_id
                        """
                    ),
                    {
                        "tenant_id": TENANT_A,
                        "company_id": item.company_id,
                        "problem_class": item.problem_class,
                        "rollout_id": item.rollout_id,
                    },
                )
        finally:
            await session.rollback()
            await session.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_uncommitted_rollout_is_not_visible_after_transaction_abort() -> None:
    item = identity("transaction-abort")
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    try:
        transaction = await session.begin()
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(TENANT_A)},
        )
        await activate(session, item)
        await transaction.rollback()
    finally:
        await session.close()
        await engine.dispose()

    async with runtime_session(TENANT_A) as restarted_session:
        repository = PostgresEpistemicRolloutRepository(restarted_session)
        assert await repository.get(identity=item) is None
