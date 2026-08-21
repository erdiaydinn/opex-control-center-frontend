"""Persist Jarvis epistemic canary rollout authority and append-only receipts.

Revision ID: 0052_jarvis_epistemic_rollout_authority
Revises: 0051_jarvis_agent_control_plane
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0052_jarvis_epistemic_rollout_authority"
down_revision: str | None = "0051_jarvis_agent_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "jarvis_epistemic_rollouts",
    "jarvis_epistemic_rollout_receipts",
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
        CREATE TABLE jarvis_epistemic_rollouts (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            company_id varchar(255) NOT NULL,
            problem_class varchar(255) NOT NULL,
            rollout_id varchar(255) NOT NULL,
            generation bigint NOT NULL,
            state varchar(32) NOT NULL,
            version bigint NOT NULL DEFAULT 0,
            candidate_fingerprint char(64) NOT NULL,
            baseline_fingerprint char(64) NOT NULL,
            baseline_profile_fingerprint char(64) NOT NULL,
            selected_profile_fingerprint char(64) NOT NULL,
            activation_fingerprint char(64) NOT NULL,
            rollback_fingerprint char(64),
            snapshot_fingerprint char(64) NOT NULL,
            snapshot_payload_json text NOT NULL,
            snapshot_payload_hash char(64) NOT NULL,
            last_sequence bigint NOT NULL DEFAULT 0,
            last_event_hash char(64) NOT NULL DEFAULT repeat('0', 64),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, company_id, problem_class, rollout_id),
            CONSTRAINT ck_jarvis_epistemic_rollout_state CHECK (
                state IN ('active', 'rolled_back')
            ),
            CONSTRAINT ck_jarvis_epistemic_rollout_generation CHECK (generation >= 1),
            CONSTRAINT ck_jarvis_epistemic_rollout_version CHECK (version >= 0),
            CONSTRAINT ck_jarvis_epistemic_rollout_sequence CHECK (last_sequence >= 0),
            CONSTRAINT ck_jarvis_epistemic_rollout_fingerprints CHECK (
                candidate_fingerprint ~ '^[0-9a-f]{64}$' AND
                baseline_fingerprint ~ '^[0-9a-f]{64}$' AND
                baseline_profile_fingerprint ~ '^[0-9a-f]{64}$' AND
                selected_profile_fingerprint ~ '^[0-9a-f]{64}$' AND
                activation_fingerprint ~ '^[0-9a-f]{64}$' AND
                snapshot_fingerprint ~ '^[0-9a-f]{64}$' AND
                snapshot_payload_hash ~ '^[0-9a-f]{64}$' AND
                last_event_hash ~ '^[0-9a-f]{64}$' AND
                (rollback_fingerprint IS NULL OR
                 rollback_fingerprint ~ '^[0-9a-f]{64}$')
            ),
            CONSTRAINT ck_jarvis_epistemic_rollout_selection CHECK (
                (state = 'active' AND rollback_fingerprint IS NULL AND
                 selected_profile_fingerprint = candidate_fingerprint)
                OR
                (state = 'rolled_back' AND rollback_fingerprint IS NOT NULL AND
                 selected_profile_fingerprint = baseline_profile_fingerprint)
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_epistemic_rollout_receipts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            company_id varchar(255) NOT NULL,
            problem_class varchar(255) NOT NULL,
            rollout_id varchar(255) NOT NULL,
            sequence bigint NOT NULL,
            generation bigint NOT NULL,
            receipt_type varchar(40) NOT NULL,
            receipt_fingerprint char(64) NOT NULL,
            payload_json text NOT NULL,
            payload_hash char(64) NOT NULL,
            idempotency_key varchar(240),
            previous_event_hash char(64) NOT NULL,
            event_hash char(64) NOT NULL,
            occurred_at timestamptz NOT NULL,
            CONSTRAINT fk_jarvis_epistemic_receipt_rollout
                FOREIGN KEY (tenant_id, company_id, problem_class, rollout_id)
                REFERENCES jarvis_epistemic_rollouts(
                    tenant_id, company_id, problem_class, rollout_id
                ) ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_epistemic_receipt_sequence
                UNIQUE (tenant_id, company_id, problem_class, rollout_id, sequence),
            CONSTRAINT uq_jarvis_epistemic_receipt_fingerprint
                UNIQUE (tenant_id, company_id, problem_class, rollout_id, receipt_fingerprint),
            CONSTRAINT uq_jarvis_epistemic_receipt_event_hash
                UNIQUE (tenant_id, company_id, problem_class, rollout_id, event_hash),
            CONSTRAINT ck_jarvis_epistemic_receipt_generation CHECK (generation >= 1),
            CONSTRAINT ck_jarvis_epistemic_receipt_sequence CHECK (sequence >= 1),
            CONSTRAINT ck_jarvis_epistemic_receipt_type CHECK (
                receipt_type IN (
                    'activation',
                    'health_observation',
                    'health_verdict',
                    'rollback',
                    'promotion_evidence',
                    'promotion_approval',
                    'promotion_review'
                )
            ),
            CONSTRAINT ck_jarvis_epistemic_receipt_fingerprints CHECK (
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
        CREATE UNIQUE INDEX uq_jarvis_epistemic_receipt_idempotency
        ON jarvis_epistemic_rollout_receipts (
            tenant_id, company_id, problem_class, rollout_id, receipt_type, idempotency_key
        )
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_jarvis_epistemic_receipt_health_history
        ON jarvis_epistemic_rollout_receipts (
            tenant_id, company_id, problem_class, rollout_id, generation, sequence
        )
        WHERE receipt_type IN ('health_observation', 'health_verdict')
        """
    )
    op.execute(
        """
        CREATE INDEX ix_jarvis_epistemic_receipt_promotion_history
        ON jarvis_epistemic_rollout_receipts (
            tenant_id, company_id, problem_class, rollout_id, generation, sequence
        )
        WHERE receipt_type IN (
            'promotion_evidence', 'promotion_approval', 'promotion_review'
        )
        """
    )

    for table in TABLES:
        _rls(table)
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE jarvis_epistemic_rollouts TO opex_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE jarvis_epistemic_rollout_receipts TO opex_runtime"
    )
    op.execute("REVOKE DELETE ON TABLE jarvis_epistemic_rollouts FROM opex_runtime")
    op.execute("REVOKE UPDATE ON TABLE jarvis_epistemic_rollout_receipts FROM opex_runtime")
    op.execute("REVOKE DELETE ON TABLE jarvis_epistemic_rollout_receipts FROM opex_runtime")


def downgrade() -> None:
    raise RuntimeError(
        "0052 Jarvis epistemic rollout authority downgrade is intentionally unsupported"
    )
