"""Allow lifecycle updates to preserve, but never assert, external Planogram truth.

Revision ID: 0033_planogram_attestation_preservation
Revises: 0032_planogram_execution_assignment_hardening
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_planogram_attestation_preservation"
down_revision: str = "0032_planogram_execution_assignment_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION planogram_plan_runtime_attestation_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_user = 'opex_runtime' THEN
                IF TG_OP = 'INSERT' AND NEW.physical_truth_attested THEN
                    RAISE EXCEPTION 'Runtime role cannot assert Planogram physical truth';
                END IF;
                IF TG_OP = 'UPDATE'
                   AND NEW.physical_truth_attested
                   AND NOT COALESCE(OLD.physical_truth_attested, FALSE)
                THEN
                    RAISE EXCEPTION 'Runtime role cannot assert Planogram physical truth';
                END IF;
            END IF;
            RETURN NEW;
        END; $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION planogram_plan_runtime_attestation_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_user = 'opex_runtime' AND NEW.physical_truth_attested THEN
                RAISE EXCEPTION 'Runtime role cannot assert Planogram physical truth';
            END IF;
            RETURN NEW;
        END; $$
        """
    )
