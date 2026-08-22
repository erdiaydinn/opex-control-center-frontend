"""Persist exact-version Jarvis robot execution leases.

Revision ID: 0054_jarvis_robot_execution_leases
Revises: 0053_jarvis_robot_registry

A lease pins one mission to one immutable robot version and one registry
generation. It is not approval or business execution authority. Any registry
generation/version drift makes the lease stale and therefore unusable at the
final commit fence. Registry activation/rollback atomically revokes old active
leases at the PostgreSQL boundary.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0054_jarvis_robot_execution_leases"
down_revision: str | None = "0053_jarvis_robot_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "jarvis_robot_execution_leases",
    "jarvis_robot_execution_lease_receipts",
)


def _rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "{table}_tenant_isolation" ON "{table}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)'''
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE jarvis_robot_execution_leases (
            tenant_id uuid NOT NULL,
            company_id varchar(255) NOT NULL,
            objective_id varchar(255) NOT NULL,
            robot_id varchar(255) NOT NULL,
            lease_id char(64) NOT NULL,
            mission_id varchar(255) NOT NULL,
            robot_version bigint NOT NULL,
            registry_generation bigint NOT NULL,
            version_fingerprint char(64) NOT NULL,
            approval_evidence_ref varchar(1024) NOT NULL,
            lease_generation bigint NOT NULL DEFAULT 1,
            state varchar(32) NOT NULL DEFAULT 'active',
            canary boolean NOT NULL DEFAULT false,
            baseline_version bigint,
            baseline_version_fingerprint char(64),
            request_fingerprint char(64) NOT NULL,
            idempotency_key varchar(240) NOT NULL,
            issued_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            revocation_reason varchar(255),
            last_sequence bigint NOT NULL DEFAULT 0,
            last_event_hash char(64) NOT NULL DEFAULT repeat('0', 64),
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, lease_id),
            CONSTRAINT fk_jarvis_robot_execution_registry
                FOREIGN KEY (tenant_id, company_id, objective_id, robot_id)
                REFERENCES jarvis_robot_registries(
                    tenant_id, company_id, objective_id, robot_id
                ) ON DELETE RESTRICT,
            CONSTRAINT fk_jarvis_robot_execution_version
                FOREIGN KEY (
                    tenant_id, company_id, objective_id, robot_id, robot_version
                ) REFERENCES jarvis_robot_versions(
                    tenant_id, company_id, objective_id, robot_id, robot_version
                ) ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_robot_execution_idempotency
                UNIQUE (tenant_id, company_id, objective_id, robot_id, idempotency_key),
            CONSTRAINT ck_jarvis_robot_execution_state CHECK (
                state IN ('active', 'revoked', 'completed')
            ),
            CONSTRAINT ck_jarvis_robot_execution_positive CHECK (
                robot_version >= 1 AND registry_generation >= 1 AND lease_generation >= 1
                AND last_sequence >= 0
            ),
            CONSTRAINT ck_jarvis_robot_execution_times CHECK (expires_at > issued_at),
            CONSTRAINT ck_jarvis_robot_execution_hashes CHECK (
                lease_id ~ '^[0-9a-f]{64}$' AND
                version_fingerprint ~ '^[0-9a-f]{64}$' AND
                request_fingerprint ~ '^[0-9a-f]{64}$' AND
                last_event_hash ~ '^[0-9a-f]{64}$' AND
                (baseline_version_fingerprint IS NULL OR
                 baseline_version_fingerprint ~ '^[0-9a-f]{64}$')
            ),
            CONSTRAINT ck_jarvis_robot_execution_canary_baseline CHECK (
                (canary = false AND baseline_version IS NULL AND
                 baseline_version_fingerprint IS NULL)
                OR
                (canary = true AND baseline_version IS NOT NULL AND
                 baseline_version >= 1 AND baseline_version < robot_version AND
                 baseline_version_fingerprint IS NOT NULL)
            ),
            CONSTRAINT ck_jarvis_robot_execution_revocation CHECK (
                (state = 'active' AND revoked_at IS NULL AND revocation_reason IS NULL)
                OR
                (state = 'revoked' AND revoked_at IS NOT NULL AND
                 revocation_reason IS NOT NULL)
                OR state = 'completed'
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_robot_execution_lease_receipts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            lease_id char(64) NOT NULL,
            sequence bigint NOT NULL,
            lease_generation bigint NOT NULL,
            receipt_type varchar(32) NOT NULL,
            receipt_fingerprint char(64) NOT NULL,
            payload_json text NOT NULL,
            payload_hash char(64) NOT NULL,
            previous_event_hash char(64) NOT NULL,
            event_hash char(64) NOT NULL,
            occurred_at timestamptz NOT NULL,
            CONSTRAINT fk_jarvis_robot_execution_lease_receipt
                FOREIGN KEY (tenant_id, lease_id)
                REFERENCES jarvis_robot_execution_leases(tenant_id, lease_id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_robot_execution_lease_receipt_sequence
                UNIQUE (tenant_id, lease_id, sequence),
            CONSTRAINT uq_jarvis_robot_execution_lease_receipt_fingerprint
                UNIQUE (tenant_id, lease_id, receipt_fingerprint),
            CONSTRAINT ck_jarvis_robot_execution_lease_receipt_type CHECK (
                receipt_type IN ('issued', 'validated', 'revoked', 'completed')
            ),
            CONSTRAINT ck_jarvis_robot_execution_lease_receipt_positive CHECK (
                sequence >= 1 AND lease_generation >= 1
            ),
            CONSTRAINT ck_jarvis_robot_execution_lease_receipt_hashes CHECK (
                receipt_fingerprint ~ '^[0-9a-f]{64}$' AND
                payload_hash ~ '^[0-9a-f]{64}$' AND
                previous_event_hash ~ '^[0-9a-f]{64}$' AND
                event_hash ~ '^[0-9a-f]{64}$'
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_jarvis_robot_execution_active_registry_generation
        ON jarvis_robot_execution_leases (
            tenant_id, company_id, objective_id, robot_id,
            registry_generation, state
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION revoke_stale_jarvis_robot_execution_leases()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.generation IS DISTINCT FROM OLD.generation
               OR NEW.active_version IS DISTINCT FROM OLD.active_version
               OR NEW.active_version_fingerprint IS DISTINCT FROM OLD.active_version_fingerprint
               OR NEW.state IS DISTINCT FROM OLD.state THEN
                UPDATE jarvis_robot_execution_leases
                SET state = 'revoked',
                    lease_generation = lease_generation + 1,
                    revoked_at = NEW.updated_at,
                    revocation_reason = 'registry_generation_advanced',
                    updated_at = NEW.updated_at
                WHERE tenant_id = NEW.tenant_id
                  AND company_id = NEW.company_id
                  AND objective_id = NEW.objective_id
                  AND robot_id = NEW.robot_id
                  AND state = 'active'
                  AND (
                    registry_generation IS DISTINCT FROM NEW.generation
                    OR robot_version IS DISTINCT FROM NEW.active_version
                    OR version_fingerprint IS DISTINCT FROM NEW.active_version_fingerprint
                  );
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_revoke_stale_jarvis_robot_execution_leases
        AFTER UPDATE OF generation, active_version, active_version_fingerprint, state
        ON jarvis_robot_registries
        FOR EACH ROW
        EXECUTE FUNCTION revoke_stale_jarvis_robot_execution_leases()
        """
    )

    for table in TABLES:
        _rls(table)
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE jarvis_robot_execution_leases TO opex_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE jarvis_robot_execution_lease_receipts TO opex_runtime"
    )
    op.execute("REVOKE DELETE ON TABLE jarvis_robot_execution_leases FROM opex_runtime")
    op.execute(
        "REVOKE UPDATE ON TABLE jarvis_robot_execution_lease_receipts FROM opex_runtime"
    )
    op.execute(
        "REVOKE DELETE ON TABLE jarvis_robot_execution_lease_receipts FROM opex_runtime"
    )


def downgrade() -> None:
    raise RuntimeError(
        "0054 Jarvis robot execution lease downgrade is intentionally unsupported"
    )
