"""Harden Jarvis agent authority persistence.

Revision ID: 0052_jarvis_agent_authority_hardening
Revises: 0051_jarvis_agent_control_plane
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0052_jarvis_agent_authority_hardening"
down_revision: str | None = "0051_jarvis_agent_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_TABLES = (
    "jarvis_agent_budget_transactions",
    "jarvis_agent_budget_events",
    "jarvis_agent_commit_permits",
    "jarvis_agent_commit_events",
)


def _rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY "{table}_tenant_isolation" ON "{table}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def _append_only(table: str) -> None:
    _rls(table)
    op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')
    op.execute(f'GRANT SELECT, INSERT ON TABLE "{table}" TO opex_runtime')
    op.execute(f'REVOKE UPDATE, DELETE ON TABLE "{table}" FROM opex_runtime')


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE jarvis_agent_jobs
            ALTER COLUMN objective_ref TYPE varchar(4000),
            ADD CONSTRAINT ck_jarvis_agent_job_objective_length
                CHECK (char_length(objective_ref) BETWEEN 3 AND 4000)
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_accounts
            ADD COLUMN account_id varchar(255),
            ADD COLUMN root_account_id varchar(255),
            ADD COLUMN parent_account_id varchar(255),
            ADD COLUMN cost_delegated bigint NOT NULL DEFAULT 0,
            ADD COLUMN cost_unknown_effect_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN token_delegated bigint NOT NULL DEFAULT 0,
            ADD COLUMN token_unknown_effect_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN wall_time_limit bigint NOT NULL DEFAULT 0,
            ADD COLUMN wall_time_reserved bigint NOT NULL DEFAULT 0,
            ADD COLUMN wall_time_consumed bigint NOT NULL DEFAULT 0,
            ADD COLUMN wall_time_delegated bigint NOT NULL DEFAULT 0,
            ADD COLUMN wall_time_unknown_effect_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN transition_delegated bigint NOT NULL DEFAULT 0,
            ADD COLUMN transition_unknown_effect_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN tool_call_delegated bigint NOT NULL DEFAULT 0,
            ADD COLUMN tool_call_unknown_effect_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN descendant_consumed integer NOT NULL DEFAULT 0,
            ADD COLUMN descendant_delegated integer NOT NULL DEFAULT 0,
            ADD COLUMN descendant_unknown_effect_held integer NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        UPDATE jarvis_agent_budget_accounts
        SET account_id = root_job_id::text,
            root_account_id = root_job_id::text
        WHERE account_id IS NULL OR root_account_id IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_accounts
            ALTER COLUMN account_id SET NOT NULL,
            ALTER COLUMN root_account_id SET NOT NULL,
            DROP CONSTRAINT ck_jarvis_budget_nonnegative
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_reservations
            DROP CONSTRAINT fk_jarvis_budget_reservation_account
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_accounts
            DROP CONSTRAINT jarvis_agent_budget_accounts_pkey
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_accounts
            ADD CONSTRAINT jarvis_agent_budget_accounts_pkey
                PRIMARY KEY (tenant_id, account_id),
            ADD CONSTRAINT uq_jarvis_budget_root_membership
                UNIQUE (tenant_id, root_job_id, root_account_id, account_id),
            ADD CONSTRAINT uq_jarvis_budget_job_account
                UNIQUE (tenant_id, root_job_id, account_id),
            ADD CONSTRAINT fk_jarvis_budget_parent
                FOREIGN KEY (
                    tenant_id, root_job_id, root_account_id, parent_account_id
                )
                REFERENCES jarvis_agent_budget_accounts(
                    tenant_id, root_job_id, root_account_id, account_id
                )
                ON DELETE RESTRICT,
            ADD CONSTRAINT ck_jarvis_budget_conservation CHECK (
                cost_limit >= 0 AND cost_reserved >= 0 AND cost_consumed >= 0
                    AND cost_delegated >= 0
                    AND cost_reserved + cost_consumed + cost_delegated <= cost_limit
                    AND cost_unknown_effect_held BETWEEN 0 AND cost_reserved
                AND token_limit >= 0 AND token_reserved >= 0 AND token_consumed >= 0
                    AND token_delegated >= 0
                    AND token_reserved + token_consumed + token_delegated <= token_limit
                    AND token_unknown_effect_held BETWEEN 0 AND token_reserved
                AND wall_time_limit >= 0 AND wall_time_reserved >= 0
                    AND wall_time_consumed >= 0 AND wall_time_delegated >= 0
                    AND wall_time_reserved + wall_time_consumed + wall_time_delegated
                        <= wall_time_limit
                    AND wall_time_unknown_effect_held BETWEEN 0 AND wall_time_reserved
                AND transition_limit >= 0 AND transition_reserved >= 0
                    AND transition_consumed >= 0 AND transition_delegated >= 0
                    AND transition_reserved + transition_consumed + transition_delegated
                        <= transition_limit
                    AND transition_unknown_effect_held BETWEEN 0 AND transition_reserved
                AND tool_call_limit >= 0 AND tool_call_reserved >= 0
                    AND tool_call_consumed >= 0 AND tool_call_delegated >= 0
                    AND tool_call_reserved + tool_call_consumed + tool_call_delegated
                        <= tool_call_limit
                    AND tool_call_unknown_effect_held BETWEEN 0 AND tool_call_reserved
                AND descendant_limit >= 0 AND descendant_reserved >= 0
                    AND descendant_consumed >= 0 AND descendant_delegated >= 0
                    AND descendant_reserved + descendant_consumed + descendant_delegated
                        <= descendant_limit
                    AND descendant_unknown_effect_held BETWEEN 0 AND descendant_reserved
            ),
            ADD CONSTRAINT ck_jarvis_budget_root_identity CHECK (
                (parent_account_id IS NULL AND account_id = root_account_id)
                OR
                (parent_account_id IS NOT NULL AND account_id <> root_account_id)
            )
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_reservations
            ADD COLUMN account_id varchar(255),
            ADD COLUMN reservation_ref varchar(500),
            ADD COLUMN wall_time_units bigint NOT NULL DEFAULT 0,
            ADD COLUMN cost_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN token_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN wall_time_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN transition_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN tool_call_held bigint NOT NULL DEFAULT 0,
            ADD COLUMN descendant_held integer NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        UPDATE jarvis_agent_budget_reservations
        SET account_id = root_job_id::text,
            reservation_ref = 'legacy://' || id::text
        WHERE account_id IS NULL OR reservation_ref IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_budget_reservations
            ALTER COLUMN account_id SET NOT NULL,
            ALTER COLUMN reservation_ref SET NOT NULL,
            ADD CONSTRAINT fk_jarvis_budget_reservation_account_v2
                FOREIGN KEY (tenant_id, root_job_id, account_id)
                REFERENCES jarvis_agent_budget_accounts(
                    tenant_id, root_job_id, account_id
                )
                ON DELETE RESTRICT,
            ADD CONSTRAINT uq_jarvis_budget_reservation_ref
                UNIQUE (tenant_id, account_id, reservation_ref),
            ADD CONSTRAINT ck_jarvis_budget_reservation_v2 CHECK (
                cost_units >= 0 AND token_units >= 0 AND wall_time_units >= 0
                AND transition_units >= 0 AND tool_call_units >= 0
                AND descendant_units >= 0
                AND cost_held BETWEEN 0 AND cost_units
                AND token_held BETWEEN 0 AND token_units
                AND wall_time_held BETWEEN 0 AND wall_time_units
                AND transition_held BETWEEN 0 AND transition_units
                AND tool_call_held BETWEEN 0 AND tool_call_units
                AND descendant_held BETWEEN 0 AND descendant_units
                AND state IN ('reserved', 'unknown_effect', 'consumed', 'released')
            )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_budget_transactions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            transaction_id varchar(255) NOT NULL,
            root_account_id varchar(255) NOT NULL,
            idempotency_key varchar(240) NOT NULL,
            request_fingerprint char(64) NOT NULL,
            result_fingerprint char(64) NOT NULL,
            result_accounts jsonb NOT NULL,
            committed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_jarvis_budget_transaction_root
                FOREIGN KEY (tenant_id, root_account_id)
                REFERENCES jarvis_agent_budget_accounts(tenant_id, account_id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_budget_transaction_id
                UNIQUE (tenant_id, transaction_id),
            CONSTRAINT uq_jarvis_budget_transaction_idempotency
                UNIQUE (tenant_id, root_account_id, idempotency_key),
            CONSTRAINT ck_jarvis_budget_transaction_fingerprints CHECK (
                request_fingerprint ~ '^[0-9a-f]{64}$'
                AND result_fingerprint ~ '^[0-9a-f]{64}$'
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_budget_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            transaction_id varchar(255) NOT NULL,
            root_account_id varchar(255) NOT NULL,
            account_id varchar(255) NOT NULL,
            reservation_ref varchar(500),
            mutation_kind varchar(40) NOT NULL,
            amount jsonb NOT NULL,
            before_version bigint NOT NULL,
            after_version bigint NOT NULL,
            event_fingerprint char(64) NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_jarvis_budget_event_account
                FOREIGN KEY (tenant_id, account_id)
                REFERENCES jarvis_agent_budget_accounts(tenant_id, account_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_jarvis_budget_event_transaction
                FOREIGN KEY (tenant_id, transaction_id)
                REFERENCES jarvis_agent_budget_transactions(tenant_id, transaction_id)
                DEFERRABLE INITIALLY DEFERRED,
            CONSTRAINT uq_jarvis_budget_event_fingerprint
                UNIQUE (tenant_id, event_fingerprint),
            CONSTRAINT ck_jarvis_budget_event_kind CHECK (
                mutation_kind IN (
                    'reserve', 'consume', 'release', 'hold_unknown_effect',
                    'resolve_unknown_effect', 'allocate_child'
                )
            ),
            CONSTRAINT ck_jarvis_budget_event_version CHECK (
                before_version >= 0 AND after_version = before_version + 1
            ),
            CONSTRAINT ck_jarvis_budget_event_fingerprint CHECK (
                event_fingerprint ~ '^[0-9a-f]{64}$'
            )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_commit_fences
            ALTER COLUMN lease_id TYPE varchar(255),
            ADD COLUMN job_id uuid,
            ADD COLUMN root_job_id uuid,
            ADD COLUMN authorization_fingerprint char(64),
            ADD COLUMN request_fingerprint char(64),
            ADD COLUMN permit_id char(64),
            ADD COLUMN consumed_at timestamptz
        """
    )
    op.execute(
        """
        UPDATE jarvis_agent_commit_fences
        SET state = 'legacy_quarantined'
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_commit_fences
            ADD CONSTRAINT fk_jarvis_commit_fence_job
                FOREIGN KEY (tenant_id, job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id)
                ON DELETE RESTRICT,
            ADD CONSTRAINT fk_jarvis_commit_fence_root_job
                FOREIGN KEY (tenant_id, root_job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id)
                ON DELETE RESTRICT,
            ADD CONSTRAINT ck_jarvis_commit_fence_authority_v2 CHECK (
                state = 'legacy_quarantined'
                OR (
                    job_id IS NOT NULL
                    AND root_job_id IS NOT NULL
                    AND idempotency_key ~ '^[0-9a-f]{64}$'
                    AND authorization_fingerprint ~ '^[0-9a-f]{64}$'
                    AND request_fingerprint ~ '^[0-9a-f]{64}$'
                    AND (permit_id IS NULL OR permit_id ~ '^[0-9a-f]{64}$')
                    AND state IN (
                        'active', 'consumed', 'verified_commit', 'rejected',
                        'unknown_effect', 'reconciled_no_effect'
                    )
                )
            )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_commit_permits (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            permit_id char(64) NOT NULL,
            job_id uuid NOT NULL,
            root_job_id uuid NOT NULL,
            resource_ref varchar(500) NOT NULL,
            idempotency_key char(64) NOT NULL,
            lease_id varchar(255) NOT NULL,
            lease_generation bigint NOT NULL,
            fencing_token bigint NOT NULL,
            cancellation_epoch bigint NOT NULL,
            authorization_fingerprint char(64) NOT NULL,
            request_fingerprint char(64) NOT NULL,
            issued_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_jarvis_commit_permit_job
                FOREIGN KEY (tenant_id, job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_jarvis_commit_permit_root_job
                FOREIGN KEY (tenant_id, root_job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_commit_permit
                UNIQUE (tenant_id, permit_id),
            CONSTRAINT uq_jarvis_commit_permit_idempotency
                UNIQUE (tenant_id, idempotency_key),
            CONSTRAINT ck_jarvis_commit_permit_binding CHECK (
                permit_id ~ '^[0-9a-f]{64}$'
                AND idempotency_key ~ '^[0-9a-f]{64}$'
                AND authorization_fingerprint ~ '^[0-9a-f]{64}$'
                AND request_fingerprint ~ '^[0-9a-f]{64}$'
                AND lease_generation > 0
                AND fencing_token > 0
                AND cancellation_epoch >= 0
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jarvis_agent_commit_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            permit_id char(64) NOT NULL,
            event_type varchar(40) NOT NULL,
            transaction_ref varchar(500),
            evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
            error_code varchar(255),
            receipt_fingerprint char(64),
            event_fingerprint char(64) NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_jarvis_commit_event_permit
                FOREIGN KEY (tenant_id, permit_id)
                REFERENCES jarvis_agent_commit_permits(tenant_id, permit_id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_jarvis_commit_event_type
                UNIQUE (tenant_id, permit_id, event_type),
            CONSTRAINT uq_jarvis_commit_event_fingerprint
                UNIQUE (tenant_id, event_fingerprint),
            CONSTRAINT ck_jarvis_commit_event_type CHECK (
                event_type IN (
                    'consumed', 'verified_commit', 'rejected',
                    'unknown_effect', 'reconciled_no_effect'
                )
            ),
            CONSTRAINT ck_jarvis_commit_event_fingerprint CHECK (
                event_fingerprint ~ '^[0-9a-f]{64}$'
                AND (
                    receipt_fingerprint IS NULL
                    OR receipt_fingerprint ~ '^[0-9a-f]{64}$'
                )
            )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_workers
            ADD COLUMN job_id uuid,
            ADD COLUMN runtime_kind varchar(30),
            ADD COLUMN tenant_namespace varchar(255),
            ADD COLUMN attestation_policy_ref varchar(500),
            ADD COLUMN request_fingerprint char(64),
            ADD COLUMN worker_fingerprint char(64),
            ADD COLUMN version bigint NOT NULL DEFAULT 0,
            ADD COLUMN revocation_generation bigint NOT NULL DEFAULT 0,
            ADD COLUMN updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )
    op.execute(
        """
        UPDATE jarvis_agent_workers
        SET state = 'legacy_quarantined'
        """
    )
    op.execute(
        """
        ALTER TABLE jarvis_agent_workers
            ADD CONSTRAINT fk_jarvis_worker_job
                FOREIGN KEY (tenant_id, job_id)
                REFERENCES jarvis_agent_jobs(tenant_id, id)
                ON DELETE RESTRICT,
            ADD CONSTRAINT ck_jarvis_worker_binding_v2 CHECK (
                state = 'legacy_quarantined'
                OR (
                    job_id IS NOT NULL
                    AND runtime_kind IN ('kubernetes', 'docker')
                    AND tenant_namespace = 'tenant:' || tenant_id::text
                    AND NULLIF(attestation_policy_ref, '') IS NOT NULL
                    AND request_fingerprint ~ '^[0-9a-f]{64}$'
                    AND worker_fingerprint ~ '^[0-9a-f]{64}$'
                    AND image_digest
                        ~ '^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$'
                    AND state IN (
                        'provisioning', 'ready', 'unhealthy', 'revoked',
                        'stopped', 'recovery_required'
                    )
                )
                AND version >= 0
                AND revocation_generation >= 0
            )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_jarvis_agent_workers_active
        ON jarvis_agent_workers (tenant_id, worker_id, generation DESC)
        WHERE state NOT IN ('revoked', 'stopped', 'legacy_quarantined')
        """
    )
    op.execute(
        """
        CREATE FUNCTION jarvis_agent_worker_identity_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        BEGIN
            IF (
                NEW.tenant_id,
                NEW.worker_id,
                NEW.job_id,
                NEW.runtime_instance_ref,
                NEW.runtime_kind,
                NEW.image_digest,
                NEW.workload_identity,
                NEW.tenant_namespace,
                NEW.attestation_policy_ref,
                NEW.request_fingerprint,
                NEW.attestation_fingerprint,
                NEW.generation,
                NEW.created_at
            ) IS DISTINCT FROM (
                OLD.tenant_id,
                OLD.worker_id,
                OLD.job_id,
                OLD.runtime_instance_ref,
                OLD.runtime_kind,
                OLD.image_digest,
                OLD.workload_identity,
                OLD.tenant_namespace,
                OLD.attestation_policy_ref,
                OLD.request_fingerprint,
                OLD.attestation_fingerprint,
                OLD.generation,
                OLD.created_at
            ) THEN
                RAISE EXCEPTION 'jarvis_worker_identity_is_immutable';
            END IF;
            RETURN NEW;
        END;
        $body$
        """
    )
    op.execute(
        """
        CREATE TRIGGER jarvis_agent_worker_identity_guard
        BEFORE UPDATE ON jarvis_agent_workers
        FOR EACH ROW
        EXECUTE FUNCTION jarvis_agent_worker_identity_immutable()
        """
    )
    for table in APPEND_ONLY_TABLES:
        _append_only(table)


def downgrade() -> None:
    raise RuntimeError(
        "0052 Jarvis agent authority hardening downgrade is intentionally unsupported"
    )
