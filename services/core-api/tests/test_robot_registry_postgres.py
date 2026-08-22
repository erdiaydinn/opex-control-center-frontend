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

from app.robot_registry_repository import (
    PostgresRobotRegistryRepository,
    RobotRegistryIdentity,
)

DATABASE_URL = os.getenv("OPEX_DATABASE_URL")
MIGRATION_DATABASE_URL = os.getenv("OPEX_MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not MIGRATION_DATABASE_URL,
    reason="PostgreSQL acceptance environment is not configured",
)

TENANT_A = UUID("00000000-0000-4000-8000-0000000000a1")
TENANT_B = UUID("00000000-0000-4000-8000-0000000000b1")
NOW = datetime(2026, 8, 23, 1, 15, tzinfo=UTC)
OUTCOME = "a" * 64
SOURCE = "b" * 64
CANDIDATE_V8 = "c" * 64
REGISTRY_CANDIDATE_V8 = "d" * 64
CANDIDATE_V9 = "e" * 64
REGISTRY_CANDIDATE_V9 = "f" * 64


def _driver_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
async def seed_tenants() -> None:
    if not MIGRATION_DATABASE_URL:
        return
    connection = await asyncpg.connect(_driver_url(MIGRATION_DATABASE_URL))
    try:
        for tenant_id, slug in ((TENANT_A, "robot-a"), (TENANT_B, "robot-b")):
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


def identity(robot_id: str, tenant_id: UUID = TENANT_A) -> RobotRegistryIdentity:
    return RobotRegistryIdentity(
        tenant_id=tenant_id,
        company_id="company-a",
        objective_id="daily-report",
        robot_id=robot_id,
    )


def manifest(version: int) -> dict[str, str]:
    return {
        "method": "GET",
        "url": f"https://api.acme.example/v{version}/reports/daily",
        "operation_id": f"getDailyReportV{version}",
    }


async def register_v8(
    repository: PostgresRobotRegistryRepository,
    item: RobotRegistryIdentity,
):
    return await repository.register_version(
        identity=item,
        robot_version=8,
        parent_version=None,
        parent_version_fingerprint=None,
        kind="api",
        semantic_intent="download-daily-report",
        capability_ref="reports.download",
        manifest=manifest(8),
        expected_outcome_fingerprint=OUTCOME,
        source_robot_fingerprint=SOURCE,
        candidate_fingerprint=CANDIDATE_V8,
        registry_candidate_fingerprint=REGISTRY_CANDIDATE_V8,
        approval_evidence_ref="approval://robot/v8",
        occurred_at=NOW,
        idempotency_key="register-v8",
    )


async def register_v9(
    repository: PostgresRobotRegistryRepository,
    item: RobotRegistryIdentity,
    parent_fingerprint: str,
):
    return await repository.register_version(
        identity=item,
        robot_version=9,
        parent_version=8,
        parent_version_fingerprint=parent_fingerprint,
        kind="api",
        semantic_intent="download-daily-report",
        capability_ref="reports.download",
        manifest=manifest(9),
        expected_outcome_fingerprint=OUTCOME,
        source_robot_fingerprint=CANDIDATE_V8,
        candidate_fingerprint=CANDIDATE_V9,
        registry_candidate_fingerprint=REGISTRY_CANDIDATE_V9,
        approval_evidence_ref="approval://robot/v9",
        occurred_at=NOW + timedelta(minutes=1),
        idempotency_key="register-v9",
    )


def test_migration_is_force_rls_append_only_and_generation_fenced() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/0053_jarvis_robot_registry.py"
    ).read_text()
    assert "jarvis_robot_registries" in migration
    assert "jarvis_robot_versions" in migration
    assert "jarvis_robot_registry_receipts" in migration
    assert migration.count("FORCE ROW LEVEL SECURITY") >= 1
    assert "generation bigint NOT NULL DEFAULT 0" in migration
    assert "revision bigint NOT NULL DEFAULT 0" in migration
    assert "REVOKE UPDATE ON TABLE jarvis_robot_versions" in migration
    assert "REVOKE DELETE ON TABLE jarvis_robot_versions" in migration
    assert "REVOKE UPDATE ON TABLE jarvis_robot_registry_receipts" in migration
    assert "REVOKE DELETE ON TABLE jarvis_robot_registry_receipts" in migration


@pytest.mark.asyncio
async def test_registered_versions_and_active_selection_survive_restart() -> None:
    item = identity("restart-lineage")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        version8, _, created8 = await register_v8(repository, item)
        version9, _, created9 = await register_v9(repository, item, version8.version_fingerprint)
        registry, _, activated = await repository.activate_version(
            identity=item,
            robot_version=9,
            expected_generation=0,
            activation_evidence_ref="activation://approved/v9",
            occurred_at=NOW + timedelta(minutes=2),
            idempotency_key="activate-v9",
        )
        assert created8 is True
        assert created9 is True
        assert activated is True
        assert registry.active_version == 9
        assert registry.generation == 1
        assert version9.parent_version_fingerprint == version8.version_fingerprint

    async with runtime_session(TENANT_A) as restarted_session:
        restarted = PostgresRobotRegistryRepository(restarted_session)
        active = await restarted.get_active(identity=item)
        assert active is not None
        registry, version = active
        assert registry.active_version == 9
        assert registry.generation == 1
        assert version.robot_version == 9
        assert version.verified_manifest()["operation_id"] == "getDailyReportV9"
        versions = await restarted.list_versions(identity=item)
        assert [entry.robot_version for entry in versions] == [8, 9]
        assert await restarted.verify_journal(identity=item) is True


@pytest.mark.asyncio
async def test_exact_registration_replay_is_idempotent_and_conflict_is_rejected() -> None:
    item = identity("registration-replay")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        first, first_receipt, created = await register_v8(repository, item)
        replay, replay_receipt, replay_created = await register_v8(repository, item)
        assert created is True
        assert replay_created is False
        assert replay.version_fingerprint == first.version_fingerprint
        assert replay_receipt.receipt_fingerprint == first_receipt.receipt_fingerprint
        receipts = await repository.list_receipts(identity=item)
        assert len(receipts) == 1

        with pytest.raises(ValueError, match="conflicting_version_replay"):
            await repository.register_version(
                identity=item,
                robot_version=8,
                parent_version=None,
                parent_version_fingerprint=None,
                kind="api",
                semantic_intent="different-intent",
                capability_ref="reports.download",
                manifest=manifest(8),
                expected_outcome_fingerprint=OUTCOME,
                source_robot_fingerprint=SOURCE,
                candidate_fingerprint=CANDIDATE_V8,
                registry_candidate_fingerprint=REGISTRY_CANDIDATE_V8,
                approval_evidence_ref="approval://robot/v8",
                occurred_at=NOW,
            )


@pytest.mark.asyncio
async def test_lineage_requires_exact_next_version_and_parent_fingerprint() -> None:
    item = identity("lineage-fencing")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        version8, _, _ = await register_v8(repository, item)

        with pytest.raises(ValueError, match="increment_exactly_once"):
            await repository.register_version(
                identity=item,
                robot_version=10,
                parent_version=8,
                parent_version_fingerprint=version8.version_fingerprint,
                kind="api",
                semantic_intent="download-daily-report",
                capability_ref="reports.download",
                manifest=manifest(10),
                expected_outcome_fingerprint=OUTCOME,
                source_robot_fingerprint=CANDIDATE_V8,
                candidate_fingerprint=CANDIDATE_V9,
                registry_candidate_fingerprint=REGISTRY_CANDIDATE_V9,
                approval_evidence_ref="approval://robot/v10",
                occurred_at=NOW + timedelta(minutes=1),
            )

        with pytest.raises(ValueError, match="parent_fingerprint_mismatch"):
            await register_v9(repository, item, "9" * 64)


@pytest.mark.asyncio
async def test_activation_is_generation_fenced_and_stale_writer_is_rejected() -> None:
    item = identity("activation-cas")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        version8, _, _ = await register_v8(repository, item)
        await register_v9(repository, item, version8.version_fingerprint)
        registry, _, _ = await repository.activate_version(
            identity=item,
            robot_version=8,
            expected_generation=0,
            activation_evidence_ref="activation://v8",
            occurred_at=NOW + timedelta(minutes=2),
        )
        assert registry.generation == 1

        with pytest.raises(ValueError, match="stale_generation"):
            await repository.activate_version(
                identity=item,
                robot_version=9,
                expected_generation=0,
                activation_evidence_ref="activation://v9-stale",
                occurred_at=NOW + timedelta(minutes=3),
            )

        registry2, _, _ = await repository.activate_version(
            identity=item,
            robot_version=9,
            expected_generation=1,
            activation_evidence_ref="activation://v9",
            occurred_at=NOW + timedelta(minutes=4),
        )
        assert registry2.active_version == 9
        assert registry2.generation == 2


@pytest.mark.asyncio
async def test_rollback_moves_pointer_without_mutating_newer_version() -> None:
    item = identity("rollback-lineage")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        version8, _, _ = await register_v8(repository, item)
        version9, _, _ = await register_v9(repository, item, version8.version_fingerprint)
        active, _, _ = await repository.activate_version(
            identity=item,
            robot_version=9,
            expected_generation=0,
            activation_evidence_ref="activation://v9",
            occurred_at=NOW + timedelta(minutes=2),
        )
        rolled_back, receipt = await repository.rollback_version(
            identity=item,
            target_version=8,
            expected_generation=active.generation,
            rollback_evidence_ref="rollback://incident-42",
            occurred_at=NOW + timedelta(minutes=3),
        )
        assert rolled_back.active_version == 8
        assert rolled_back.generation == 2
        assert receipt.receipt_type == "rollback_version"
        versions = await repository.list_versions(identity=item)
        assert [entry.robot_version for entry in versions] == [8, 9]
        assert versions[1].version_fingerprint == version9.version_fingerprint
        assert await repository.verify_journal(identity=item) is True


@pytest.mark.asyncio
async def test_rollback_cannot_roll_forward_or_target_missing_version() -> None:
    item = identity("rollback-negative")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        version8, _, _ = await register_v8(repository, item)
        await register_v9(repository, item, version8.version_fingerprint)
        active, _, _ = await repository.activate_version(
            identity=item,
            robot_version=9,
            expected_generation=0,
            activation_evidence_ref="activation://v9",
            occurred_at=NOW + timedelta(minutes=2),
        )
        with pytest.raises(ValueError, match="must_target_older_version"):
            await repository.rollback_version(
                identity=item,
                target_version=9,
                expected_generation=active.generation,
                rollback_evidence_ref="rollback://same",
                occurred_at=NOW + timedelta(minutes=3),
            )
        with pytest.raises(ValueError, match="version_not_found"):
            await repository.rollback_version(
                identity=item,
                target_version=7,
                expected_generation=active.generation,
                rollback_evidence_ref="rollback://missing",
                occurred_at=NOW + timedelta(minutes=4),
            )


@pytest.mark.asyncio
async def test_force_rls_prevents_cross_tenant_registry_visibility() -> None:
    item = identity("tenant-isolation")
    async with runtime_session(TENANT_A) as session:
        repository = PostgresRobotRegistryRepository(session)
        await register_v8(repository, item)

    async with runtime_session(TENANT_B) as session:
        other_tenant_view = PostgresRobotRegistryRepository(session)
        assert await other_tenant_view.get(identity=item) is None
        assert await other_tenant_view.get_version(identity=item, robot_version=8) is None
        assert await other_tenant_view.list_receipts(identity=item) == ()


@pytest.mark.asyncio
async def test_runtime_role_cannot_mutate_immutable_versions_or_receipts() -> None:
    async with runtime_session(TENANT_A) as session:
        privileges = (
            await session.execute(
                text(
                    """
                    SELECT
                      has_table_privilege(current_user, 'jarvis_robot_versions', 'UPDATE')
                        AS version_update,
                      has_table_privilege(current_user, 'jarvis_robot_versions', 'DELETE')
                        AS version_delete,
                      has_table_privilege(
                        current_user, 'jarvis_robot_registry_receipts', 'UPDATE'
                      ) AS receipt_update,
                      has_table_privilege(
                        current_user, 'jarvis_robot_registry_receipts', 'DELETE'
                      ) AS receipt_delete
                    """
                )
            )
        ).mappings().one()
        assert privileges["version_update"] is False
        assert privileges["version_delete"] is False
        assert privileges["receipt_update"] is False
        assert privileges["receipt_delete"] is False
