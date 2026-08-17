from __future__ import annotations

import os

import asyncpg
import pytest

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"
DNA_DRAFT = "31111111-1111-4111-8111-111111111111"
DNA_ATTESTED = "32222222-2222-4222-8222-222222222222"
DNA_DIRECT = "33333333-3333-4333-8333-333333333333"
PLAN_ATTESTED = "41111111-1111-4111-8111-111111111111"
PLAN_DIRECT_DRAFT = "42222222-2222-4222-8222-222222222222"
SHA_A = "a" * 64
SHA_B = "b" * 64
PLAN_JSON = (
    '{"aisles":[{"aisle_id":"A01","modules":[{"module_id":"M1",'
    '"shelves":[{"shelf_no":1,"products":[{"sku":"SKU-1",'
    '"facing_count":1}]}]}]}]}'
)
MUTATED_PLAN_JSON = (
    '{"aisles":[{"aisle_id":"A01","modules":[{"module_id":"M1",'
    '"shelves":[{"shelf_no":1,"products":[{"sku":"SKU-1",'
    '"facing_count":9}]}]}]}]}'
)


def _dsn(env_name: str) -> str:
    raw = os.environ[env_name]
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _seed_migrator() -> None:
    connection = await asyncpg.connect(_dsn("OPEX_MIGRATION_DATABASE_URL"))
    try:
        await connection.execute(
            """
            INSERT INTO tenants (id, slug, display_name)
            VALUES ($1::uuid, 'master26-a', 'Master 26 A'),
                   ($2::uuid, 'master26-b', 'Master 26 B')
            ON CONFLICT (id) DO NOTHING
            """,
            TENANT_A,
            TENANT_B,
        )
        for dna_id, store_code, sha in (
            (DNA_DRAFT, "STORE-DRAFT", SHA_A),
            (DNA_ATTESTED, "STORE-ATTESTED", SHA_B),
            (DNA_DIRECT, "STORE-DIRECT", SHA_A),
        ):
            await connection.execute(
                """
                INSERT INTO planogram_store_dna_versions (
                    id, tenant_id, store_code, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, submitted_by, submitted_at,
                    approved_by, approved_at
                ) VALUES (
                    $1::uuid, $2::uuid, $3, 1, 'warehouse_bootstrap', 'approved',
                    '{}'::jsonb, '{}'::jsonb, $4, TRUE,
                    'migrator', 'dna-maker', CURRENT_TIMESTAMP,
                    'dna-checker', CURRENT_TIMESTAMP
                )
                ON CONFLICT (tenant_id, store_code, version_number) DO NOTHING
                """,
                dna_id,
                TENANT_A,
                store_code,
                sha,
            )
        await connection.execute(
            """
            INSERT INTO planogram_plan_versions (
                id, tenant_id, store_dna_version_id, store_code, version_number,
                source, status, plan_payload, plan_fingerprint,
                optimizer_fingerprint, physical_truth_attested, created_by,
                submitted_by, submitted_at
            ) VALUES (
                $1::uuid, $2::uuid, $3::uuid, 'STORE-ATTESTED', 1,
                'optimizer_preview', 'submitted', $4::jsonb, $5, $6,
                TRUE, 'external-attestation-fixture', 'plan-maker', CURRENT_TIMESTAMP
            )
            ON CONFLICT (id) DO NOTHING
            """,
            PLAN_ATTESTED,
            TENANT_A,
            DNA_ATTESTED,
            PLAN_JSON,
            SHA_A,
            SHA_B,
        )
        await connection.execute(
            """
            INSERT INTO planogram_plan_versions (
                id, tenant_id, store_dna_version_id, store_code, version_number,
                source, status, plan_payload, plan_fingerprint,
                optimizer_fingerprint, physical_truth_attested, created_by
            ) VALUES (
                $1::uuid, $2::uuid, $3::uuid, 'STORE-DIRECT', 1,
                'optimizer_preview', 'draft', $4::jsonb, $5, $6,
                TRUE, 'external-attestation-fixture'
            )
            ON CONFLICT (id) DO NOTHING
            """,
            PLAN_DIRECT_DRAFT,
            TENANT_A,
            DNA_DIRECT,
            PLAN_JSON,
            SHA_B,
            SHA_A,
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_master26_postgres_truth_and_rls_guards() -> None:
    await _seed_migrator()
    runtime = await asyncpg.connect(_dsn("OPEX_DATABASE_URL"))
    try:
        await runtime.execute("SELECT set_config('app.tenant_id', $1, false)", TENANT_A)

        draft_id = await runtime.fetchval(
            """
            INSERT INTO planogram_plan_versions (
                tenant_id, store_dna_version_id, store_code, version_number,
                source, plan_payload, plan_fingerprint, optimizer_fingerprint,
                created_by
            ) VALUES (
                $1::uuid, $2::uuid, 'STORE-DRAFT', 1, 'optimizer_preview',
                $3::jsonb, $4, $5, 'runtime-maker'
            )
            RETURNING id
            """,
            TENANT_A,
            DNA_DRAFT,
            PLAN_JSON,
            SHA_A,
            SHA_B,
        )
        assert draft_id is not None

        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute(
                "UPDATE planogram_plan_versions "
                "SET physical_truth_attested=TRUE WHERE id=$1",
                draft_id,
            )

        with pytest.raises(
            asyncpg.PostgresError,
            match="draft may only remain draft or become submitted",
        ):
            await runtime.execute(
                """
                UPDATE planogram_plan_versions
                SET status='approved', approved_by='runtime-checker',
                    approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=$1::uuid
                """,
                PLAN_DIRECT_DRAFT,
            )

        await runtime.execute(
            """
            UPDATE planogram_plan_versions
            SET status='submitted', submitted_by='runtime-maker',
                submitted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=$1
            """,
            draft_id,
        )

        with pytest.raises(
            asyncpg.PostgresError,
            match="Submitted Planogram candidate payload is immutable",
        ):
            await runtime.execute(
                """
                UPDATE planogram_plan_versions
                SET plan_payload=$1::jsonb, plan_fingerprint=$2,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=$3
                """,
                MUTATED_PLAN_JSON,
                SHA_B,
                draft_id,
            )

        with pytest.raises(
            asyncpg.PostgresError,
            match="physical-truth attestation",
        ):
            await runtime.execute(
                """
                UPDATE planogram_plan_versions
                SET status='approved', approved_by='runtime-checker',
                    approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=$1
                """,
                draft_id,
            )

        # External authority seeded TRUE; runtime may preserve it while completing
        # maker-checker lifecycle, but it still cannot assert FALSE -> TRUE itself.
        await runtime.execute(
            """
            UPDATE planogram_plan_versions
            SET status='approved', approved_by='plan-checker',
                approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=$1::uuid
            """,
            PLAN_ATTESTED,
        )
        approved = await runtime.fetchrow(
            "SELECT status, physical_truth_attested "
            "FROM planogram_plan_versions WHERE id=$1::uuid",
            PLAN_ATTESTED,
        )
        assert approved is not None
        assert approved["status"] == "approved"
        assert approved["physical_truth_attested"] is True

        assignment_id = await runtime.fetchval(
            """
            INSERT INTO planogram_execution_assignments (
                tenant_id, plan_version_id, store_code, assigned_by, effective_from
            ) VALUES (
                $1::uuid, $2::uuid, 'STORE-ATTESTED', 'assigner', CURRENT_TIMESTAMP
            )
            RETURNING id
            """,
            TENANT_A,
            PLAN_ATTESTED,
        )
        assert assignment_id is not None

        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute(
                "UPDATE planogram_execution_assignments "
                "SET plan_version_id=$1::uuid WHERE id=$2",
                draft_id,
                assignment_id,
            )

        await runtime.execute(
            """
            UPDATE planogram_execution_assignments
            SET status='acknowledged', acknowledged_by='store-user',
                acknowledged_at=CURRENT_TIMESTAMP
            WHERE id=$1
            """,
            assignment_id,
        )
        await runtime.execute(
            """
            UPDATE planogram_execution_assignments
            SET status='closed', closed_by='checker', closed_at=CURRENT_TIMESTAMP
            WHERE id=$1
            """,
            assignment_id,
        )
        with pytest.raises(
            asyncpg.PostgresError,
            match="Closed Planogram execution assignment",
        ):
            await runtime.execute(
                "UPDATE planogram_execution_assignments "
                "SET status='acknowledged' WHERE id=$1",
                assignment_id,
            )

        await runtime.execute("SELECT set_config('app.tenant_id', $1, false)", TENANT_B)
        assert (
            await runtime.fetchval(
                "SELECT COUNT(*) FROM planogram_execution_assignments WHERE id=$1",
                assignment_id,
            )
            == 0
        )
        assert (
            await runtime.fetchval(
                "SELECT COUNT(*) FROM planogram_plan_versions WHERE id=$1::uuid",
                PLAN_ATTESTED,
            )
            == 0
        )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_master26_schema_is_force_rls_and_compliance_is_bound_to_field() -> None:
    connection = await asyncpg.connect(_dsn("OPEX_MIGRATION_DATABASE_URL"))
    try:
        for table_name in (
            "planogram_plan_versions",
            "planogram_plan_events",
            "planogram_execution_assignments",
            "planogram_execution_events",
            "planogram_compliance_observations",
        ):
            row = await connection.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid=$1::regclass",
                table_name,
            )
            assert row is not None
            assert row["relrowsecurity"] is True
            assert row["relforcerowsecurity"] is True

        assert await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname='fk_planogram_compliance_field_promotion'
                  AND conrelid='planogram_compliance_observations'::regclass
            )
            """
        )
        assert await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname='trg_planogram_assignment_identity'
                  AND NOT tgisinternal
            )
            """
        )
        assert await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname='trg_planogram_compliance_observations_append_only'
                  AND NOT tgisinternal
            )
            """
        )
    finally:
        await connection.close()
