from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.robot_execution_lease_repository import PostgresRobotExecutionLeaseRepository
from app.robot_registry_repository import PostgresRobotRegistryRepository, RobotRegistryIdentity

DATABASE_URL = os.getenv("OPEX_DATABASE_URL")
MIGRATION_DATABASE_URL = os.getenv("OPEX_MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not MIGRATION_DATABASE_URL,
    reason="PostgreSQL acceptance environment is not configured",
)

TENANT_A = UUID("00000000-0000-4000-8000-0000000000a1")
TENANT_B = UUID("00000000-0000-4000-8000-0000000000b1")
NOW = datetime(2026, 8, 23, 2, 0, tzinfo=UTC)
OUTCOME = "a" * 64
SOURCE = "b" * 64


def _driver_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
async def seed_tenants() -> None:
    if not MIGRATION_DATABASE_URL:
        return
    connection = await asyncpg.connect(_driver_url(MIGRATION_DATABASE_URL))
    try:
        for tenant_id, slug in ((TENANT_A, "lease-a"), (TENANT_B, "lease-b")):
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


def identity(robot_id: str) -> RobotRegistryIdentity:
    return RobotRegistryIdentity(
        tenant_id=TENANT_A,
        company_id="company-a",
        objective_id="daily-report",
        robot_id=robot_id,
    )


async def prepare_active_v9(session: AsyncSession, robot_id: str):
    item = identity(robot_id)
    registry_repo = PostgresRobotRegistryRepository(session)
    v8, _, _ = await registry_repo.register_version(
        identity=item,
        robot_version=8,
        parent_version=None,
        parent_version_fingerprint=None,
        kind="api",
        semantic_intent="download-daily-report",
        capability_ref="reports.download",
        manifest={
            "method": "GET",
            "url": "https://api.acme.example/v8/reports/daily",
            "operation_id": "getDailyReportV8",
        },
        expected_outcome_fingerprint=OUTCOME,
        source_robot_fingerprint=SOURCE,
        candidate_fingerprint="c" * 64,
        registry_candidate_fingerprint="d" * 64,
        approval_evidence_ref="approval://robot/v8",
        occurred_at=NOW,
    )
    v9, _, _ = await registry_repo.register_version(
        identity=item,
        robot_version=9,
        parent_version=8,
        parent_version_fingerprint=v8.version_fingerprint,
        kind="api",
        semantic_intent="download-daily-report",
        capability_ref="reports.download",
        manifest={
            "method": "GET",
            "url": "https://api.acme.example/v9/reports/daily",
            "operation_id": "getDailyReportV9",
        },
        expected_outcome_fingerprint=OUTCOME,
        source_robot_fingerprint=v8.version_fingerprint,
        candidate_fingerprint="e" * 64,
        registry_candidate_fingerprint="f" * 64,
        approval_evidence_ref="approval://robot/v9",
        occurred_at=NOW + timedelta(minutes=1),
    )
    active, _, _ = await registry_repo.activate_version(
        identity=item,
        robot_version=9,
        expected_generation=0,
        activation_evidence_ref="activation://robot/v9",
        occurred_at=NOW + timedelta(minutes=2),
    )
    return item, registry_repo, v8, v9, active


def test_migration_has_force_rls_generation_pin_and_registry_revocation_trigger():
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/0054_jarvis_robot_execution_leases.py"
    ).read_text()
    assert "jarvis_robot_execution_leases" in migration
    assert "jarvis_robot_execution_lease_receipts" in migration
    assert "registry_generation bigint NOT NULL" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "trg_revoke_stale_jarvis_robot_execution_leases" in migration
    assert "registry_generation IS DISTINCT FROM NEW.generation" in migration
    assert "REVOKE UPDATE ON TABLE jarvis_robot_execution_lease_receipts" in migration
    assert "REVOKE DELETE ON TABLE jarvis_robot_execution_lease_receipts" in migration


@pytest.mark.asyncio
async def test_issue_replay_and_current_validation_are_exact_version_bound():
    async with runtime_session(TENANT_A) as session:
        item, _, v8, v9, active = await prepare_active_v9(session, "lease-current")
        leases = PostgresRobotExecutionLeaseRepository(session)
        lease, issued_receipt, created = await leases.issue(
            identity=item,
            mission_id="mission-daily-report",
            expected_robot_version=9,
            expected_registry_generation=active.generation,
            expected_version_fingerprint=v9.version_fingerprint,
            approval_evidence_ref=v9.approval_evidence_ref,
            issued_at=NOW + timedelta(minutes=3),
            expires_at=NOW + timedelta(hours=1),
            idempotency_key="mission-daily-report-v9",
            canary=True,
            baseline_version=8,
            baseline_version_fingerprint=v8.version_fingerprint,
        )
        replay, replay_receipt, replay_created = await leases.issue(
            identity=item,
            mission_id="mission-daily-report",
            expected_robot_version=9,
            expected_registry_generation=active.generation,
            expected_version_fingerprint=v9.version_fingerprint,
            approval_evidence_ref=v9.approval_evidence_ref,
            issued_at=NOW + timedelta(minutes=3),
            expires_at=NOW + timedelta(hours=1),
            idempotency_key="mission-daily-report-v9",
            canary=True,
            baseline_version=8,
            baseline_version_fingerprint=v8.version_fingerprint,
        )
        assert created is True
        assert replay_created is False
        assert replay.lease_id == lease.lease_id
        assert replay_receipt.receipt_fingerprint == issued_receipt.receipt_fingerprint
        current = await leases.validate_current(
            tenant_id=TENANT_A,
            lease_id=lease.lease_id,
            checked_at=NOW + timedelta(minutes=4),
        )
        assert current.state == "active"
        assert current.robot_version == 9
        assert current.registry_generation == active.generation
        assert current.version_fingerprint == v9.version_fingerprint
        assert [receipt.receipt_type for receipt in await leases.list_receipts(
            tenant_id=TENANT_A, lease_id=lease.lease_id
        )] == ["issued", "validated"]


@pytest.mark.asyncio
async def test_stale_generation_cannot_issue_execution_lease():
    async with runtime_session(TENANT_A) as session:
        item, _, _, v9, active = await prepare_active_v9(session, "lease-stale-issue")
        leases = PostgresRobotExecutionLeaseRepository(session)
        with pytest.raises(ValueError, match="registry_pin_mismatch"):
            await leases.issue(
                identity=item,
                mission_id="mission-stale",
                expected_robot_version=9,
                expected_registry_generation=active.generation - 1,
                expected_version_fingerprint=v9.version_fingerprint,
                approval_evidence_ref=v9.approval_evidence_ref,
                issued_at=NOW + timedelta(minutes=3),
                expires_at=NOW + timedelta(hours=1),
                idempotency_key="mission-stale-v9",
            )


@pytest.mark.asyncio
async def test_registry_rollback_atomically_revokes_old_execution_lease():
    async with runtime_session(TENANT_A) as session:
        item, registry_repo, v8, v9, active = await prepare_active_v9(
            session, "lease-rollback"
        )
        leases = PostgresRobotExecutionLeaseRepository(session)
        lease, _, _ = await leases.issue(
            identity=item,
            mission_id="mission-rollback",
            expected_robot_version=9,
            expected_registry_generation=active.generation,
            expected_version_fingerprint=v9.version_fingerprint,
            approval_evidence_ref=v9.approval_evidence_ref,
            issued_at=NOW + timedelta(minutes=3),
            expires_at=NOW + timedelta(hours=1),
            idempotency_key="mission-rollback-v9",
        )
        rolled_back, _ = await registry_repo.rollback_version(
            identity=item,
            target_version=8,
            expected_generation=active.generation,
            rollback_evidence_ref="rollback://canary-health",
            occurred_at=NOW + timedelta(minutes=5),
        )
        assert rolled_back.active_version == 8
        assert rolled_back.active_version_fingerprint == v8.version_fingerprint
        stale = await leases.get(TENANT_A, lease.lease_id)
        assert stale is not None
        assert stale.state == "revoked"
        assert stale.lease_generation == lease.lease_generation + 1
        assert stale.revocation_reason == "registry_generation_advanced"
        with pytest.raises(ValueError, match="lease_not_active"):
            await leases.validate_current(
                tenant_id=TENANT_A,
                lease_id=lease.lease_id,
                checked_at=NOW + timedelta(minutes=6),
            )


@pytest.mark.asyncio
async def test_force_rls_hides_execution_lease_cross_tenant():
    lease_id = None
    async with runtime_session(TENANT_A) as session:
        item, _, _, v9, active = await prepare_active_v9(session, "lease-tenant")
        leases = PostgresRobotExecutionLeaseRepository(session)
        lease, _, _ = await leases.issue(
            identity=item,
            mission_id="mission-tenant",
            expected_robot_version=9,
            expected_registry_generation=active.generation,
            expected_version_fingerprint=v9.version_fingerprint,
            approval_evidence_ref=v9.approval_evidence_ref,
            issued_at=NOW + timedelta(minutes=3),
            expires_at=NOW + timedelta(hours=1),
            idempotency_key="mission-tenant-v9",
        )
        lease_id = lease.lease_id

    assert lease_id is not None
    async with runtime_session(TENANT_B) as session:
        foreign = PostgresRobotExecutionLeaseRepository(session)
        assert await foreign.get(TENANT_B, lease_id) is None
        assert await foreign.list_receipts(tenant_id=TENANT_B, lease_id=lease_id) == ()


@pytest.mark.asyncio
async def test_runtime_cannot_delete_leases_or_mutate_receipt_history():
    async with runtime_session(TENANT_A) as session:
        privileges = (
            await session.execute(
                text(
                    """
                    SELECT
                      has_table_privilege(
                        current_user, 'jarvis_robot_execution_leases', 'DELETE'
                      ) AS lease_delete,
                      has_table_privilege(
                        current_user, 'jarvis_robot_execution_lease_receipts', 'UPDATE'
                      ) AS receipt_update,
                      has_table_privilege(
                        current_user, 'jarvis_robot_execution_lease_receipts', 'DELETE'
                      ) AS receipt_delete
                    """
                )
            )
        ).mappings().one()
        assert privileges["lease_delete"] is False
        assert privileges["receipt_update"] is False
        assert privileges["receipt_delete"] is False
