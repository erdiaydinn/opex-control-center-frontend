from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
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

TENANT = UUID("00000000-0000-4000-8000-0000000000c1")


def _driver_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_database_rejects_secret_bearing_robot_manifest() -> None:
    assert DATABASE_URL is not None
    assert MIGRATION_DATABASE_URL is not None
    migrator = await asyncpg.connect(_driver_url(MIGRATION_DATABASE_URL))
    try:
        await migrator.execute(
            """
            INSERT INTO tenants (id, slug, display_name)
            VALUES ($1, 'robot-secret-boundary', 'Robot Secret Boundary')
            ON CONFLICT (id) DO NOTHING
            """,
            TENANT,
        )
    finally:
        await migrator.close()

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    identity = RobotRegistryIdentity(
        tenant_id=TENANT,
        company_id="company-a",
        objective_id="daily-report",
        robot_id="secret-bearing-robot",
    )
    try:
        with pytest.raises((IntegrityError, DBAPIError), match="secret_free"):
            async with maker() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": str(TENANT)},
                )
                repository = PostgresRobotRegistryRepository(session)
                await repository.register_version(
                    identity=identity,
                    robot_version=1,
                    parent_version=None,
                    parent_version_fingerprint=None,
                    kind="api",
                    semantic_intent="download-report",
                    capability_ref="reports.download",
                    manifest={
                        "method": "GET",
                        "url": "https://api.acme.example/v1/reports",
                        "operation_id": "getReports",
                        "authorization": "Bearer must-never-persist",
                    },
                    expected_outcome_fingerprint="a" * 64,
                    source_robot_fingerprint="b" * 64,
                    candidate_fingerprint="c" * 64,
                    registry_candidate_fingerprint="d" * 64,
                    approval_evidence_ref="approval://security-test",
                    occurred_at=datetime(2026, 8, 23, 1, 30, tzinfo=UTC),
                )
    finally:
        await engine.dispose()
