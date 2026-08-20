"""Add durable Jarvis hierarchical-agent control plane.

Revision ID: 0051_jarvis_agent_control_plane
Revises: 0050_academy_credential_authority
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0051_jarvis_agent_control_plane"
down_revision: str | None = "0050_academy_credential_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "jarvis_agent_jobs",
    "jarvis_agent_job_events",
    "jarvis_agent_budget_accounts",
    "jarvis_agent_budget_reservations",
    "jarvis_agent_commit_fences",
    "jarvis_agent_workers",
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
        CREATE TABLE jarvis_agent_jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            requested_by varchar(255) NOT NULL,
            idempotency_key varchar(240) NOT NULL,
            request_fingerprint char(64) NOT NULL,
            objective_ref varchar(500) NOT NULL,
            admission_fingerprint char(64),
            status varchar(40) NOT NULL DEFAULT 'queued',
            version bigint NOT NULL DEFAULT 1,
            cancellation_epoch bigint NOT NULL DEFAULT 0,
            required_child_count integer NOT NULL,
            completed_child_count integer NOT NULL DEFAULT 0,
            effect_state varchar(40) NOT NULL DEFAULT 'no_effect',
            last_checkpoint_ref varchar(500),
            last_event_hash char(64) NOT NULL DEFAULT repeat('0', 64),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            terminal_at timestamptz,
            CONSTRAINT uq_jarvis_agent_job_request
                UNIQUE (tenant_id, requested_by, idempotency_key),
            CONSTRAINT uq_jarvis_agent_job_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_jarvis_agent_job_fingerprints CHECK (
                request_fingerprint ~ '^[0-9a-f]{64}$' AND
                (admission_fingerprint IS NULL OR admission_fingerprint ~ '^[0-9a-f]{64}$')
            ),
            CONSTRAINT ck_jarvis_agent_job_counts CHECK (
                required_child_count BETWEEN 1 AND 512 AND
                completed_child_count BETWEEN 0 AND required_child_count
            ),
            CONSTRAINT ck_jarvis_agent_job_version CHECK (version >= 1),
            CONSTRAINT ck_jarvis_agent_job_cancel_epoch CHECK (cancellation_epoch >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_job_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            job_id uuid NOT NULL,
            sequence bigint NOT NULL,
            event_type varchar(60) NOT NULL,
            actor_ref varchar(255) NOT NULL,
            cancellation_epoch bigint NOT NULL,
            evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
            previous_event_hash char(64) NOT NULL,
            event_hash char(64) NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_jarvis_agent_event_job FOREIGN KEY (tenant_id, job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_agent_event_sequence UNIQUE (tenant_id, job_id, sequence),
            CONSTRAINT uq_jarvis_agent_event_hash UNIQUE (tenant_id, event_hash),
            CONSTRAINT ck_jarvis_agent_event_hashes CHECK (
                previous_event_hash ~ '^[0-9a-f]{64}$' AND event_hash ~ '^[0-9a-f]{64}$'
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_budget_accounts (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            root_job_id uuid NOT NULL,
            version bigint NOT NULL DEFAULT 0,
            cost_limit bigint NOT NULL,
            cost_reserved bigint NOT NULL DEFAULT 0,
            cost_consumed bigint NOT NULL DEFAULT 0,
            token_limit bigint NOT NULL,
            token_reserved bigint NOT NULL DEFAULT 0,
            token_consumed bigint NOT NULL DEFAULT 0,
            transition_limit bigint NOT NULL,
            transition_reserved bigint NOT NULL DEFAULT 0,
            transition_consumed bigint NOT NULL DEFAULT 0,
            tool_call_limit bigint NOT NULL,
            tool_call_reserved bigint NOT NULL DEFAULT 0,
            tool_call_consumed bigint NOT NULL DEFAULT 0,
            descendant_limit integer NOT NULL,
            descendant_reserved integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, root_job_id),
            CONSTRAINT fk_jarvis_budget_job FOREIGN KEY (tenant_id, root_job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_jarvis_budget_nonnegative CHECK (
                cost_limit >= cost_reserved AND
                cost_reserved >= cost_consumed AND cost_consumed >= 0 AND
                token_limit >= token_reserved AND
                token_reserved >= token_consumed AND token_consumed >= 0 AND
                transition_limit >= transition_reserved AND
                transition_reserved >= transition_consumed AND transition_consumed >= 0 AND
                tool_call_limit >= tool_call_reserved AND
                tool_call_reserved >= tool_call_consumed AND tool_call_consumed >= 0 AND
                descendant_limit >= descendant_reserved AND descendant_reserved >= 0
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_budget_reservations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            root_job_id uuid NOT NULL,
            child_job_ref varchar(255) NOT NULL,
            idempotency_key varchar(240) NOT NULL,
            request_fingerprint char(64) NOT NULL,
            cost_units bigint NOT NULL,
            token_units bigint NOT NULL,
            transition_units bigint NOT NULL,
            tool_call_units bigint NOT NULL,
            descendant_units integer NOT NULL,
            state varchar(30) NOT NULL DEFAULT 'reserved',
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_jarvis_budget_reservation_account FOREIGN KEY (tenant_id, root_job_id)
                REFERENCES jarvis_agent_budget_accounts(tenant_id, root_job_id) ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_budget_reservation_key
                UNIQUE (tenant_id, root_job_id, idempotency_key),
            CONSTRAINT ck_jarvis_budget_reservation_nonnegative CHECK (
                cost_units >= 0 AND token_units >= 0 AND transition_units >= 0 AND
                tool_call_units >= 0 AND descendant_units >= 0
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_commit_fences (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            resource_ref varchar(500) NOT NULL,
            fencing_token bigint NOT NULL,
            lease_id char(64) NOT NULL,
            lease_generation bigint NOT NULL,
            cancellation_epoch bigint NOT NULL,
            idempotency_key varchar(500) NOT NULL,
            state varchar(30) NOT NULL DEFAULT 'active',
            effect_receipt_ref varchar(500),
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, resource_ref),
            CONSTRAINT uq_jarvis_commit_fence_idempotency UNIQUE (tenant_id, idempotency_key),
            CONSTRAINT ck_jarvis_commit_fence_positive CHECK (
                fencing_token > 0 AND lease_generation > 0 AND cancellation_epoch >= 0
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_workers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            worker_id varchar(255) NOT NULL,
            runtime_instance_ref varchar(500) NOT NULL,
            image_digest varchar(255) NOT NULL,
            workload_identity varchar(500) NOT NULL,
            attestation_fingerprint char(64) NOT NULL,
            generation bigint NOT NULL,
            state varchar(30) NOT NULL,
            heartbeat_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_jarvis_agent_worker UNIQUE (tenant_id, worker_id, generation),
            CONSTRAINT ck_jarvis_agent_worker_generation CHECK (generation > 0),
            CONSTRAINT ck_jarvis_agent_worker_attestation
                CHECK (attestation_fingerprint ~ '^[0-9a-f]{64}$')
        )
        """
    )
    for table in TABLES:
        _rls(table)
    for table in TABLES:
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')
        op.execute(f'GRANT SELECT, INSERT, UPDATE ON TABLE "{table}" TO opex_runtime')
    op.execute("REVOKE DELETE ON TABLE jarvis_agent_job_events FROM opex_runtime")
    op.execute("REVOKE UPDATE ON TABLE jarvis_agent_job_events FROM opex_runtime")


def downgrade() -> None:
    raise RuntimeError("0051 Jarvis agent control-plane downgrade is intentionally unsupported")
