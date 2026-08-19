"""Converge tamper-evident per-tenant audit chains on the current platform.

Revision ID: 0045_jarvis_audit_hash_chain
Revises: 0044_external_acceptance_evidence

This is tamper-evident PostgreSQL evidence, not a WORM claim. A database owner
can replace functions/triggers; independently signed/immutable anchoring remains
a separate external control.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045_jarvis_audit_hash_chain"
down_revision: str | None = "0044_external_acceptance_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
GENESIS_HASH = "0" * 64


def upgrade() -> None:
    op.execute("ALTER TABLE public.audit_events ADD COLUMN chain_sequence bigint")
    op.execute(
        "ALTER TABLE public.audit_events ADD COLUMN previous_event_hash varchar(64)"
    )
    op.execute("ALTER TABLE public.audit_events ADD COLUMN event_hash varchar(64)")
    op.execute("ALTER TABLE public.audit_events ADD COLUMN event_payload text")

    # Existing audit rows span tenants and FORCE RLS also applies to the owner.
    # Exclude runtime traffic for the deterministic backfill and restore FORCE
    # RLS before this migration transaction can commit.
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE public.audit_events NO FORCE ROW LEVEL SECURITY")

    op.execute(
        r"""
        CREATE FUNCTION public.audit_event_payload_v1(
            p_id uuid,
            p_tenant_id uuid,
            p_actor_subject text,
            p_action text,
            p_resource_type text,
            p_resource_id text,
            p_decision text,
            p_request_id text,
            p_data jsonb,
            p_created_at timestamptz
        ) RETURNS text
        LANGUAGE sql
        IMMUTABLE
        SET search_path = pg_catalog, public
        AS $$
            SELECT jsonb_build_object(
                'version', 1,
                'event_id', p_id::text,
                'tenant_id', p_tenant_id::text,
                'actor_subject', p_actor_subject,
                'action', p_action,
                'resource_type', p_resource_type,
                'resource_id', p_resource_id,
                'decision', p_decision,
                'request_id', p_request_id,
                'data', p_data,
                'created_at_utc', to_char(
                    p_created_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                )
            )::text
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION public.audit_event_hash_v1(
            p_sequence bigint,
            p_previous_hash text,
            p_payload text
        ) RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog, public
        AS $$
            SELECT encode(
                public.digest(
                    convert_to(
                        'eay-audit-chain-v1|' || p_sequence::text || '|' ||
                        p_previous_hash || '|' || p_payload,
                        'UTF8'
                    ),
                    'sha256'
                ),
                'hex'
            )
        $$
        """
    )

    op.execute(
        "ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_append_only"
    )
    op.execute(
        rf"""
        DO $$
        DECLARE
            tenant_row record;
            event_row record;
            next_sequence bigint;
            previous_hash text;
            payload text;
            computed_hash text;
        BEGIN
            FOR tenant_row IN
                SELECT DISTINCT tenant_id
                FROM public.audit_events
                ORDER BY tenant_id
            LOOP
                next_sequence := 0;
                previous_hash := '{GENESIS_HASH}';

                FOR event_row IN
                    SELECT id, tenant_id, actor_subject, action, resource_type,
                           resource_id, decision, request_id, data, created_at
                    FROM public.audit_events
                    WHERE tenant_id = tenant_row.tenant_id
                    ORDER BY created_at, id
                LOOP
                    next_sequence := next_sequence + 1;
                    payload := public.audit_event_payload_v1(
                        event_row.id,
                        event_row.tenant_id,
                        event_row.actor_subject,
                        event_row.action,
                        event_row.resource_type,
                        event_row.resource_id,
                        event_row.decision,
                        event_row.request_id,
                        event_row.data,
                        event_row.created_at
                    );
                    computed_hash := public.audit_event_hash_v1(
                        next_sequence,
                        previous_hash,
                        payload
                    );

                    UPDATE public.audit_events
                    SET chain_sequence = next_sequence,
                        previous_event_hash = previous_hash,
                        event_hash = computed_hash,
                        event_payload = payload
                    WHERE id = event_row.id;

                    previous_hash := computed_hash;
                END LOOP;
            END LOOP;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE public.audit_events ENABLE TRIGGER audit_events_append_only"
    )
    op.execute("ALTER TABLE public.audit_events FORCE ROW LEVEL SECURITY")

    for column in (
        "chain_sequence",
        "previous_event_hash",
        "event_hash",
        "event_payload",
    ):
        op.execute(
            f"ALTER TABLE public.audit_events ALTER COLUMN {column} SET NOT NULL"
        )

    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        "ck_audit_events_chain_sequence_positive CHECK (chain_sequence > 0)"
    )
    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        "ck_audit_events_previous_hash_hex "
        "CHECK (previous_event_hash ~ '^[0-9a-f]{64}$')"
    )
    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        "ck_audit_events_event_hash_hex "
        "CHECK (event_hash ~ '^[0-9a-f]{64}$')"
    )
    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        "uq_audit_events_tenant_chain_sequence "
        "UNIQUE (tenant_id, chain_sequence)"
    )
    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        "uq_audit_events_tenant_event_hash UNIQUE (tenant_id, event_hash)"
    )

    op.execute(
        rf"""
        CREATE FUNCTION public.seal_audit_event_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            last_sequence bigint;
            last_hash text;
        BEGIN
            IF NEW.chain_sequence IS NOT NULL
               OR NEW.previous_event_hash IS NOT NULL
               OR NEW.event_hash IS NOT NULL
               OR NEW.event_payload IS NOT NULL THEN
                RAISE EXCEPTION 'audit chain fields are server controlled';
            END IF;

            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.tenant_id::text, 116721)
            );

            SELECT chain_sequence, event_hash
            INTO last_sequence, last_hash
            FROM public.audit_events
            WHERE tenant_id = NEW.tenant_id
            ORDER BY chain_sequence DESC
            LIMIT 1;

            NEW.chain_sequence := COALESCE(last_sequence, 0) + 1;
            NEW.previous_event_hash := COALESCE(last_hash, '{GENESIS_HASH}');
            NEW.event_payload := public.audit_event_payload_v1(
                NEW.id,
                NEW.tenant_id,
                NEW.actor_subject,
                NEW.action,
                NEW.resource_type,
                NEW.resource_id,
                NEW.decision,
                NEW.request_id,
                NEW.data,
                NEW.created_at
            );
            NEW.event_hash := public.audit_event_hash_v1(
                NEW.chain_sequence,
                NEW.previous_event_hash,
                NEW.event_payload
            );
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_hash_chain
        BEFORE INSERT ON public.audit_events
        FOR EACH ROW EXECUTE FUNCTION public.seal_audit_event_v1()
        """
    )

    payload_signature = (
        "public.audit_event_payload_v1(uuid, uuid, text, text, text, text, "
        "text, text, jsonb, timestamptz)"
    )
    hash_signature = "public.audit_event_hash_v1(bigint, text, text)"
    seal_signature = "public.seal_audit_event_v1()"

    for signature in (payload_signature, hash_signature, seal_signature):
        op.execute(f"REVOKE EXECUTE ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {payload_signature} TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {hash_signature} TO {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS audit_events_hash_chain ON public.audit_events"
    )
    op.execute("DROP FUNCTION IF EXISTS public.seal_audit_event_v1()")
    op.execute(
        "DROP FUNCTION IF EXISTS public.audit_event_hash_v1(bigint, text, text)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "public.audit_event_payload_v1(uuid, uuid, text, text, text, text, "
        "text, text, jsonb, timestamptz)"
    )

    for constraint in (
        "uq_audit_events_tenant_event_hash",
        "uq_audit_events_tenant_chain_sequence",
        "ck_audit_events_event_hash_hex",
        "ck_audit_events_previous_hash_hex",
        "ck_audit_events_chain_sequence_positive",
    ):
        op.execute(
            f"ALTER TABLE public.audit_events DROP CONSTRAINT IF EXISTS {constraint}"
        )
    for column in (
        "event_payload",
        "event_hash",
        "previous_event_hash",
        "chain_sequence",
    ):
        op.execute(
            f"ALTER TABLE public.audit_events DROP COLUMN IF EXISTS {column}"
        )
