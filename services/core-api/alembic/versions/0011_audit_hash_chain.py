"""Add tamper-evident per-tenant audit hash chains.

Revision ID: 0011_audit_hash_chain
Revises: 0010_jarvis_idempotency
Create Date: 2026-08-12

This is tamper-evident evidence inside PostgreSQL, not a WORM guarantee.
A database owner can still replace triggers/functions; external signed
checkpoints are a separate follow-up control.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_audit_hash_chain"
down_revision: str | None = "0010_jarvis_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
GENESIS_HASH = "0" * 64


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("chain_sequence", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("event_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("event_payload", sa.Text(), nullable=True),
    )

    # Backfill must see every tenant while runtime traffic is excluded. FORCE
    # RLS also applies to the table owner, so temporarily relax FORCE only
    # under an ACCESS EXCLUSIVE lock inside this migration transaction. RLS is
    # immediately forced again before the transaction can commit.
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

    # The existing append-only trigger intentionally blocks UPDATE. Runtime is
    # excluded by the table lock, so only this deterministic migration
    # backfill may temporarily bypass that trigger.
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

    op.execute(
        "ALTER TABLE public.audit_events ALTER COLUMN chain_sequence SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE public.audit_events ALTER COLUMN previous_event_hash SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE public.audit_events ALTER COLUMN event_hash SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE public.audit_events ALTER COLUMN event_payload SET NOT NULL"
    )

    op.create_check_constraint(
        "ck_audit_events_chain_sequence_positive",
        "audit_events",
        "chain_sequence > 0",
    )
    op.create_check_constraint(
        "ck_audit_events_previous_hash_hex",
        "audit_events",
        "previous_event_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_audit_events_event_hash_hex",
        "audit_events",
        "event_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_unique_constraint(
        "uq_audit_events_tenant_chain_sequence",
        "audit_events",
        ["tenant_id", "chain_sequence"],
    )
    op.create_unique_constraint(
        "uq_audit_events_tenant_event_hash",
        "audit_events",
        ["tenant_id", "event_hash"],
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

    # The trigger function executes as invoker and calls the payload/hash
    # helpers, so runtime needs only these helper EXECUTEs in addition to its
    # existing SELECT+INSERT table privileges. The trigger itself does not
    # need to be a generally callable runtime primitive.
    op.execute(f"GRANT EXECUTE ON FUNCTION {payload_signature} TO {RUNTIME_ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION {hash_signature} TO {RUNTIME_ROLE}")


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

    op.drop_constraint(
        "uq_audit_events_tenant_event_hash",
        "audit_events",
        type_="unique",
    )
    op.drop_constraint(
        "uq_audit_events_tenant_chain_sequence",
        "audit_events",
        type_="unique",
    )
    op.drop_constraint(
        "ck_audit_events_event_hash_hex",
        "audit_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_events_previous_hash_hex",
        "audit_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_events_chain_sequence_positive",
        "audit_events",
        type_="check",
    )
    op.drop_column("audit_events", "event_payload")
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_event_hash")
    op.drop_column("audit_events", "chain_sequence")
