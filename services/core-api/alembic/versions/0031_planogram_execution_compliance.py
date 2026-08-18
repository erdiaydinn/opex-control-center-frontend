"""Add Planogram execution/compliance authority after physical truth and optimizer.

Revision ID: 0031_planogram_execution_compliance
Revises: 0030_planogram_store_dna_foundation
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_planogram_execution_compliance"
down_revision: str = "0030_planogram_store_dna_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(f"""CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE planogram_plan_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            store_dna_version_id uuid NOT NULL,
            store_code varchar(80) NOT NULL,
            version_number integer NOT NULL CHECK (version_number > 0),
            source varchar(32) NOT NULL CHECK (source IN ('optimizer_preview','manual_import')),
            status varchar(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','submitted','approved','rejected','superseded')),
            plan_payload jsonb NOT NULL,
            plan_fingerprint char(64) NOT NULL CHECK (plan_fingerprint ~ '^[0-9a-f]{64}$'),
            optimizer_fingerprint char(64),
            physical_truth_attested boolean NOT NULL DEFAULT FALSE,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_by varchar(255), submitted_at timestamptz,
            approved_by varchar(255), approved_at timestamptz,
            rejected_by varchar(255), rejected_at timestamptz, rejection_reason varchar(500),
            CONSTRAINT uq_planogram_plan_version UNIQUE (tenant_id, store_code, version_number),
            CONSTRAINT uq_planogram_plan_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT fk_planogram_plan_store_dna FOREIGN KEY (tenant_id, store_dna_version_id)
                REFERENCES planogram_store_dna_versions(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_planogram_plan_optimizer_fingerprint CHECK (
                optimizer_fingerprint IS NULL OR optimizer_fingerprint ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_planogram_plan_rejection CHECK (
                status <> 'rejected'
                OR (rejected_by IS NOT NULL AND rejected_at IS NOT NULL AND rejection_reason IS
                NOT NULL)
            )
        )
        """)
    op.execute(
        "CREATE UNIQUE INDEX uq_planogram_plan_active_edit ON planogram_plan_versions "
        "(tenant_id, store_code) WHERE status IN ('draft','submitted')"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_planogram_plan_approved ON planogram_plan_versions "
        "(tenant_id, store_code) WHERE status='approved'"
    )
    op.execute(
        "CREATE INDEX ix_planogram_plan_store_status ON planogram_plan_versions "
        "(tenant_id, store_code, status, version_number DESC)"
    )

    op.execute("""
        CREATE TABLE planogram_plan_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            plan_version_id uuid NOT NULL,
            event_type varchar(32) NOT NULL
    CHECK (event_type IN ('drafted','updated','submitted','approved','rejected','superseded')),
            actor_subject varchar(255) NOT NULL,
            from_status varchar(20), to_status varchar(20), reason varchar(500),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_planogram_plan_event FOREIGN KEY (tenant_id, plan_version_id)
                REFERENCES planogram_plan_versions(tenant_id, id) ON DELETE RESTRICT
        )
        """)

    op.execute("""
        CREATE TABLE planogram_execution_assignments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            plan_version_id uuid NOT NULL,
            store_code varchar(80) NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'assigned'
                CHECK (status IN ('assigned','acknowledged','closed')),
            assigned_by varchar(255) NOT NULL,
            assigned_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            effective_from timestamptz NOT NULL,
            due_at timestamptz,
            acknowledged_by varchar(255), acknowledged_at timestamptz,
            closed_by varchar(255), closed_at timestamptz,
            CONSTRAINT uq_planogram_assignment_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT fk_planogram_assignment_plan FOREIGN KEY (tenant_id, plan_version_id)
                REFERENCES planogram_plan_versions(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_planogram_assignment_due CHECK (due_at IS NULL OR due_at >=
            effective_from),
            CONSTRAINT ck_planogram_assignment_ack CHECK (
                status <> 'acknowledged' OR (acknowledged_by IS NOT NULL AND acknowledged_at IS
                NOT NULL)
            ),
            CONSTRAINT ck_planogram_assignment_closed CHECK (
                status <> 'closed' OR (closed_by IS NOT NULL AND closed_at IS NOT NULL)
            )
        )
        """)
    op.execute(
        "CREATE UNIQUE INDEX uq_planogram_assignment_active_store ON"
        " planogram_execution_assignments (tenant_id, store_code) WHERE status <> 'closed'"
    )
    op.execute(
        "CREATE INDEX ix_planogram_assignment_store ON planogram_execution_assignments "
        "(tenant_id, store_code, assigned_at DESC)"
    )

    op.execute("""
        CREATE TABLE planogram_execution_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            assignment_id uuid NOT NULL,
            event_type varchar(32) NOT NULL
                CHECK (event_type IN ('assigned','acknowledged','closed')),
            actor_subject varchar(255) NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_planogram_execution_event FOREIGN KEY (tenant_id, assignment_id)
                REFERENCES planogram_execution_assignments(tenant_id, id) ON DELETE RESTRICT
        )
        """)

    op.execute("""
        CREATE TABLE planogram_compliance_observations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            assignment_id uuid NOT NULL,
            plan_version_id uuid NOT NULL,
            field_promotion_id uuid NOT NULL,
            candidate_fingerprint char(64) NOT NULL CHECK (candidate_fingerprint ~
            '^[0-9a-f]{64}$'),
            sku varchar(160) NOT NULL,
            expected_locations jsonb NOT NULL,
            actual_location jsonb NOT NULL,
            result varchar(20) NOT NULL CHECK (result IN ('compliant','deviation')),
            deviation_codes varchar(64)[] NOT NULL DEFAULT ARRAY[]::varchar(64)[],
            accepted_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_planogram_compliance_promotion UNIQUE (tenant_id, field_promotion_id),
            CONSTRAINT fk_planogram_compliance_assignment FOREIGN KEY (tenant_id, assignment_id)
                REFERENCES planogram_execution_assignments(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_planogram_compliance_plan FOREIGN KEY (tenant_id, plan_version_id)
                REFERENCES planogram_plan_versions(tenant_id, id) ON DELETE RESTRICT
        )
        """)
    op.execute(
        "CREATE INDEX ix_planogram_compliance_assignment ON planogram_compliance_observations "
        "(tenant_id, assignment_id, created_at DESC)"
    )

    for table_name in (
        "planogram_plan_versions",
        "planogram_plan_events",
        "planogram_execution_assignments",
        "planogram_execution_events",
        "planogram_compliance_observations",
    ):
        _tenant_policy(table_name)

    op.execute("""
        CREATE OR REPLACE FUNCTION planogram_plan_runtime_attestation_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_user = 'opex_runtime' AND NEW.physical_truth_attested THEN
                RAISE EXCEPTION 'Runtime role cannot assert Planogram physical truth';
            END IF;
            RETURN NEW;
        END; $$
        """)
    op.execute(
        "CREATE TRIGGER trg_planogram_plan_runtime_attestation BEFORE INSERT OR UPDATE ON"
        " planogram_plan_versions FOR EACH ROW EXECUTE FUNCTION"
        " planogram_plan_runtime_attestation_guard()"
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION planogram_plan_lifecycle_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE dna_status varchar(20); dna_geometry boolean; dna_store varchar(80);
        BEGIN
            IF OLD.status = 'superseded' THEN
                RAISE EXCEPTION 'Superseded Planogram plans are immutable';
            END IF;
            IF OLD.status = 'approved' THEN
                IF NEW.status <> 'superseded'
                   OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                   OR NEW.store_dna_version_id IS DISTINCT FROM OLD.store_dna_version_id
                   OR NEW.store_code IS DISTINCT FROM OLD.store_code
                   OR NEW.version_number IS DISTINCT FROM OLD.version_number
                   OR NEW.source IS DISTINCT FROM OLD.source
                   OR NEW.plan_payload IS DISTINCT FROM OLD.plan_payload
                   OR NEW.plan_fingerprint IS DISTINCT FROM OLD.plan_fingerprint
                   OR NEW.optimizer_fingerprint IS DISTINCT FROM OLD.optimizer_fingerprint
                   OR NEW.physical_truth_attested IS DISTINCT FROM OLD.physical_truth_attested
                   OR NEW.created_by IS DISTINCT FROM OLD.created_by
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at
                   OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by
                   OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at
                   OR NEW.approved_by IS DISTINCT FROM OLD.approved_by
                   OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
                   OR NEW.rejected_by IS DISTINCT FROM OLD.rejected_by
                   OR NEW.rejected_at IS DISTINCT FROM OLD.rejected_at
                   OR NEW.rejection_reason IS DISTINCT FROM OLD.rejection_reason
    THEN RAISE EXCEPTION 'Approved Planogram plan is immutable except approved -> superseded';
                END IF;
            END IF;
            IF NEW.status = 'approved' AND OLD.status <> 'approved' THEN
                IF NOT NEW.physical_truth_attested THEN
    RAISE EXCEPTION 'Planogram approval requires external physical-truth attestation';
                END IF;
                IF NEW.submitted_by IS NULL OR NEW.approved_by IS NULL OR NEW.submitted_by =
                NEW.approved_by THEN
                    RAISE EXCEPTION 'Planogram approval requires maker-checker separation';
                END IF;
                SELECT status, geometry_attested, store_code
                INTO dna_status, dna_geometry, dna_store
                FROM planogram_store_dna_versions
                WHERE tenant_id=NEW.tenant_id AND id=NEW.store_dna_version_id;
                IF dna_status IS DISTINCT FROM 'approved' OR NOT COALESCE(dna_geometry, FALSE)
                   OR dna_store IS DISTINCT FROM NEW.store_code THEN
    RAISE EXCEPTION 'Planogram approval requires approved attested Store DNA for the same store';
                END IF;
            END IF;
            RETURN NEW;
        END; $$
        """)
    op.execute(
        "CREATE TRIGGER trg_planogram_plan_lifecycle BEFORE UPDATE ON planogram_plan_versions "
        "FOR EACH ROW EXECUTE FUNCTION planogram_plan_lifecycle_guard()"
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION planogram_assignment_approved_plan_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE plan_status varchar(20); plan_store varchar(80); attested boolean;
        BEGIN
            SELECT status, store_code, physical_truth_attested
            INTO plan_status, plan_store, attested
            FROM planogram_plan_versions
            WHERE tenant_id=NEW.tenant_id AND id=NEW.plan_version_id;
            IF plan_status IS DISTINCT FROM 'approved' OR NOT COALESCE(attested, FALSE)
               OR plan_store IS DISTINCT FROM NEW.store_code THEN
    RAISE EXCEPTION 'Execution assignment requires approved attested plan for same store';
            END IF;
            RETURN NEW;
        END; $$
        """)
    op.execute(
        "CREATE TRIGGER trg_planogram_assignment_approved_plan BEFORE INSERT ON"
        " planogram_execution_assignments FOR EACH ROW EXECUTE FUNCTION"
        " planogram_assignment_approved_plan_guard()"
    )

    for table_name in (
        "planogram_plan_events",
        "planogram_execution_events",
        "planogram_compliance_observations",
    ):
        op.execute(
            f"""CREATE OR REPLACE FUNCTION {table_name}_append_only()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION '{table_name} is append-only'; END; $$"""
        )
        op.execute(
            f"CREATE TRIGGER trg_{table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name} "
            f"FOR EACH ROW EXECUTE FUNCTION {table_name}_append_only()"
        )

    op.execute(f"GRANT SELECT ON planogram_plan_versions TO {RUNTIME_ROLE}")
    op.execute(
        "GRANT INSERT (tenant_id, store_dna_version_id, store_code, version_number, source,"
        " plan_payload, plan_fingerprint, optimizer_fingerprint, created_by) ON"
        f" planogram_plan_versions TO {RUNTIME_ROLE}"
    )
    op.execute(
        "GRANT UPDATE (status, plan_payload, plan_fingerprint, optimizer_fingerprint, updated_at,"
        " submitted_by, submitted_at, approved_by, approved_at, rejected_by, rejected_at,"
        f" rejection_reason) ON planogram_plan_versions TO {RUNTIME_ROLE}"
    )
    op.execute(f"GRANT SELECT, INSERT ON planogram_plan_events TO {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON planogram_execution_assignments TO {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON planogram_execution_events TO {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON planogram_compliance_observations TO {RUNTIME_ROLE}")


def downgrade() -> None:
    for table_name in (
        "planogram_compliance_observations",
        "planogram_execution_events",
        "planogram_plan_events",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute(f"DROP FUNCTION IF EXISTS {table_name}_append_only()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_planogram_assignment_approved_plan ON"
        " planogram_execution_assignments"
    )
    op.execute("DROP FUNCTION IF EXISTS planogram_assignment_approved_plan_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_planogram_plan_lifecycle ON planogram_plan_versions")
    op.execute("DROP FUNCTION IF EXISTS planogram_plan_lifecycle_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_planogram_plan_runtime_attestation ON planogram_plan_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS planogram_plan_runtime_attestation_guard()")
    op.execute("DROP TABLE planogram_compliance_observations")
    op.execute("DROP TABLE planogram_execution_events")
    op.execute("DROP TABLE planogram_execution_assignments")
    op.execute("DROP TABLE planogram_plan_events")
    op.execute("DROP TABLE planogram_plan_versions")
