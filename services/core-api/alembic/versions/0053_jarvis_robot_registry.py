"""Persist approved Jarvis robot versions, active selection and rollback lineage.

Revision ID: 0053_jarvis_robot_registry
Revises: 0052_jarvis_epistemic_rollout_authority

This migration creates persistence only. It does not approve candidates, execute
robots, or mint Jarvis execution authority. Version artifacts and event receipts
are append-only; the small registry pointer is the only mutable surface.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0053_jarvis_robot_registry"
down_revision: str | None = "0052_jarvis_epistemic_rollout_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "jarvis_robot_registries",
    "jarvis_robot_versions",
    "jarvis_robot_registry_receipts",
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
        CREATE TABLE jarvis_robot_registries (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            company_id varchar(255) NOT NULL,
            objective_id varchar(255) NOT NULL,
            robot_id varchar(255) NOT NULL,
            state varchar(32) NOT NULL DEFAULT 'registered',
            active_version bigint,
            active_version_fingerprint char(64),
            generation bigint NOT NULL DEFAULT 0,
            revision bigint NOT NULL DEFAULT 0,
            last_sequence bigint NOT NULL DEFAULT 0,
            last_event_hash char(64) NOT NULL DEFAULT repeat('0', 64),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, company_id, objective_id, robot_id),
            CONSTRAINT ck_jarvis_robot_registry_state CHECK (
                state IN ('registered', 'active', 'disabled')
            ),
            CONSTRAINT ck_jarvis_robot_registry_generation CHECK (generation >= 0),
            CONSTRAINT ck_jarvis_robot_registry_revision CHECK (revision >= 0),
            CONSTRAINT ck_jarvis_robot_registry_sequence CHECK (last_sequence >= 0),
            CONSTRAINT ck_jarvis_robot_registry_active_selection CHECK (
                (state = 'active' AND active_version IS NOT NULL AND
                 active_version >= 1 AND active_version_fingerprint IS NOT NULL)
                OR
                (state IN ('registered', 'disabled') AND
                 active_version IS NULL AND active_version_fingerprint IS NULL)
            ),
            CONSTRAINT ck_jarvis_robot_registry_hashes CHECK (
                last_event_hash ~ '^[0-9a-f]{64}$' AND
                (active_version_fingerprint IS NULL OR
                 active_version_fingerprint ~ '^[0-9a-f]{64}$')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_robot_versions (
            tenant_id uuid NOT NULL,
            company_id varchar(255) NOT NULL,
            objective_id varchar(255) NOT NULL,
            robot_id varchar(255) NOT NULL,
            robot_version bigint NOT NULL,
            parent_version bigint,
            parent_version_fingerprint char(64),
            kind varchar(32) NOT NULL,
            semantic_intent varchar(255) NOT NULL,
            capability_ref varchar(255) NOT NULL,
            manifest_json text NOT NULL,
            manifest_hash char(64) NOT NULL,
            expected_outcome_fingerprint char(64) NOT NULL,
            source_robot_fingerprint char(64) NOT NULL,
            candidate_fingerprint char(64) NOT NULL,
            registry_candidate_fingerprint char(64) NOT NULL,
            approval_evidence_ref varchar(1024) NOT NULL,
            version_fingerprint char(64) NOT NULL,
            registered_at timestamptz NOT NULL,
            PRIMARY KEY (
                tenant_id, company_id, objective_id, robot_id, robot_version
            ),
            CONSTRAINT fk_jarvis_robot_version_registry
                FOREIGN KEY (tenant_id, company_id, objective_id, robot_id)
                REFERENCES jarvis_robot_registries(
                    tenant_id, company_id, objective_id, robot_id
                ) ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_robot_version_fingerprint
                UNIQUE (
                    tenant_id, company_id, objective_id, robot_id,
                    version_fingerprint
                ),
            CONSTRAINT uq_jarvis_robot_candidate_fingerprint
                UNIQUE (
                    tenant_id, company_id, objective_id, robot_id,
                    candidate_fingerprint
                ),
            CONSTRAINT ck_jarvis_robot_version_number CHECK (robot_version >= 1),
            CONSTRAINT ck_jarvis_robot_parent_version CHECK (
                (parent_version IS NULL AND parent_version_fingerprint IS NULL)
                OR
                (parent_version IS NOT NULL AND parent_version >= 1 AND
                 parent_version < robot_version AND
                 parent_version_fingerprint IS NOT NULL)
            ),
            CONSTRAINT ck_jarvis_robot_version_kind CHECK (
                kind IN ('api', 'playwright', 'hybrid')
            ),
            CONSTRAINT ck_jarvis_robot_version_hashes CHECK (
                manifest_hash ~ '^[0-9a-f]{64}$' AND
                expected_outcome_fingerprint ~ '^[0-9a-f]{64}$' AND
                source_robot_fingerprint ~ '^[0-9a-f]{64}$' AND
                candidate_fingerprint ~ '^[0-9a-f]{64}$' AND
                registry_candidate_fingerprint ~ '^[0-9a-f]{64}$' AND
                version_fingerprint ~ '^[0-9a-f]{64}$' AND
                (parent_version_fingerprint IS NULL OR
                 parent_version_fingerprint ~ '^[0-9a-f]{64}$')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_robot_registry_receipts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            company_id varchar(255) NOT NULL,
            objective_id varchar(255) NOT NULL,
            robot_id varchar(255) NOT NULL,
            sequence bigint NOT NULL,
            generation bigint NOT NULL,
            receipt_type varchar(40) NOT NULL,
            robot_version bigint NOT NULL,
            receipt_fingerprint char(64) NOT NULL,
            payload_json text NOT NULL,
            payload_hash char(64) NOT NULL,
            idempotency_key varchar(240),
            previous_event_hash char(64) NOT NULL,
            event_hash char(64) NOT NULL,
            occurred_at timestamptz NOT NULL,
            CONSTRAINT fk_jarvis_robot_registry_receipt
                FOREIGN KEY (tenant_id, company_id, objective_id, robot_id)
                REFERENCES jarvis_robot_registries(
                    tenant_id, company_id, objective_id, robot_id
                ) ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_robot_registry_receipt_sequence
                UNIQUE (
                    tenant_id, company_id, objective_id, robot_id, sequence
                ),
            CONSTRAINT uq_jarvis_robot_registry_receipt_fingerprint
                UNIQUE (
                    tenant_id, company_id, objective_id, robot_id,
                    receipt_fingerprint
                ),
            CONSTRAINT uq_jarvis_robot_registry_receipt_event_hash
                UNIQUE (
                    tenant_id, company_id, objective_id, robot_id, event_hash
                ),
            CONSTRAINT ck_jarvis_robot_registry_receipt_sequence CHECK (sequence >= 1),
            CONSTRAINT ck_jarvis_robot_registry_receipt_generation CHECK (generation >= 0),
            CONSTRAINT ck_jarvis_robot_registry_receipt_version CHECK (robot_version >= 1),
            CONSTRAINT ck_jarvis_robot_registry_receipt_type CHECK (
                receipt_type IN (
                    'register_version', 'activate_version', 'rollback_version'
                )
            ),
            CONSTRAINT ck_jarvis_robot_registry_receipt_hashes CHECK (
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
        CREATE UNIQUE INDEX uq_jarvis_robot_registry_receipt_idempotency
        ON jarvis_robot_registry_receipts (
            tenant_id, company_id, objective_id, robot_id,
            receipt_type, idempotency_key
        )
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_jarvis_robot_version_lineage
        ON jarvis_robot_versions (
            tenant_id, company_id, objective_id, robot_id, robot_version
        )
        """
    )

    for table in TABLES:
        _rls(table)
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE jarvis_robot_registries TO opex_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE jarvis_robot_versions TO opex_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE jarvis_robot_registry_receipts TO opex_runtime"
    )
    op.execute("REVOKE DELETE ON TABLE jarvis_robot_registries FROM opex_runtime")
    op.execute("REVOKE UPDATE ON TABLE jarvis_robot_versions FROM opex_runtime")
    op.execute("REVOKE DELETE ON TABLE jarvis_robot_versions FROM opex_runtime")
    op.execute("REVOKE UPDATE ON TABLE jarvis_robot_registry_receipts FROM opex_runtime")
    op.execute("REVOKE DELETE ON TABLE jarvis_robot_registry_receipts FROM opex_runtime")


def downgrade() -> None:
    raise RuntimeError(
        "0053 Jarvis robot registry downgrade is intentionally unsupported"
    )
