"""Enforce Field proposer/approver/consumer separation at the database boundary.

Revision ID: 0028_field_promotion_consumer_separation
Revises: 0027_field_template_lifecycle_runtime_grant
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_field_promotion_consumer_separation"
down_revision: str = "0027_field_template_lifecycle_runtime_grant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_field_promotion_consumer_separation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            proposer text;
            field_decider text;
            field_decision text;
            expected_consumer text;
        BEGIN
            SELECT p.proposed_by, p.consumer_module, d.decided_by, d.decision
              INTO proposer, expected_consumer, field_decider, field_decision
            FROM field_promotion_requests p
            LEFT JOIN field_promotion_decisions d
              ON d.tenant_id = p.tenant_id AND d.promotion_id = p.id
            WHERE p.tenant_id = NEW.tenant_id
              AND p.id = NEW.promotion_id;

            IF proposer IS NULL THEN
                RAISE EXCEPTION 'promotion request missing';
            END IF;
            IF field_decision IS DISTINCT FROM 'approve' THEN
                RAISE EXCEPTION 'consumer handoff requires explicit Field approval';
            END IF;
            IF expected_consumer IS DISTINCT FROM NEW.consumer_module THEN
                RAISE EXCEPTION 'consumer module does not match governed adapter';
            END IF;
            IF NEW.actor_subject = proposer THEN
                RAISE EXCEPTION 'promotion proposer cannot accept consumer handoff';
            END IF;
            IF NEW.actor_subject = field_decider THEN
                RAISE EXCEPTION 'Field approver cannot also accept consumer handoff';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION enforce_field_promotion_consumer_separation() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER field_promotion_consumer_separation
        BEFORE INSERT ON field_promotion_consumer_receipts
        FOR EACH ROW EXECUTE FUNCTION enforce_field_promotion_consumer_separation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS field_promotion_consumer_separation ON"
        " field_promotion_consumer_receipts"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_field_promotion_consumer_separation()")
