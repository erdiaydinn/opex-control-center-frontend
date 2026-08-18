"""Harden Planogram execution assignment identity and runtime grants.

Revision ID: 0032_planogram_execution_assignment_hardening
Revises: 0031_planogram_execution_compliance
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032_planogram_execution_assignment_hardening"
down_revision: str = "0031_planogram_execution_compliance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.execute(f"REVOKE UPDATE ON planogram_execution_assignments FROM {RUNTIME_ROLE}")
    op.execute(
        "GRANT UPDATE (status, acknowledged_by, acknowledged_at, closed_by, closed_at) "
        f"ON planogram_execution_assignments TO {RUNTIME_ROLE}"
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION planogram_assignment_identity_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.plan_version_id IS DISTINCT FROM OLD.plan_version_id
               OR NEW.store_code IS DISTINCT FROM OLD.store_code
               OR NEW.assigned_by IS DISTINCT FROM OLD.assigned_by
               OR NEW.assigned_at IS DISTINCT FROM OLD.assigned_at
               OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
               OR NEW.due_at IS DISTINCT FROM OLD.due_at
            THEN
                RAISE EXCEPTION 'Planogram execution assignment identity is immutable';
            END IF;
            IF OLD.status = 'closed' THEN
                RAISE EXCEPTION 'Closed Planogram execution assignment is immutable';
            END IF;
            IF OLD.status = 'assigned' AND NEW.status NOT IN
            ('assigned','acknowledged','closed') THEN
                RAISE EXCEPTION 'Invalid Planogram assignment state transition';
            END IF;
            IF OLD.status = 'acknowledged' AND NEW.status NOT IN ('acknowledged','closed') THEN
                RAISE EXCEPTION 'Invalid Planogram assignment state transition';
            END IF;
            RETURN NEW;
        END; $$
        """)
    op.execute(
        "CREATE TRIGGER trg_planogram_assignment_identity BEFORE UPDATE "
        "ON planogram_execution_assignments FOR EACH ROW "
        "EXECUTE FUNCTION planogram_assignment_identity_guard()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_planogram_assignment_identity "
        "ON planogram_execution_assignments"
    )
    op.execute("DROP FUNCTION IF EXISTS planogram_assignment_identity_guard()")
    op.execute(f"REVOKE UPDATE ON planogram_execution_assignments FROM {RUNTIME_ROLE}")
    op.execute(f"GRANT UPDATE ON planogram_execution_assignments TO {RUNTIME_ROLE}")
