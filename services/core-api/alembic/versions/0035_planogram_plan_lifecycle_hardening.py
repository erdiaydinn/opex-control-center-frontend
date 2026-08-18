"""Harden Planogram plan lifecycle and submitted-candidate immutability.

Revision ID: 0035_planogram_plan_lifecycle_hardening
Revises: 0034_planogram_compliance_promotion_fk
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035_planogram_plan_lifecycle_hardening"
down_revision: str = "0034_planogram_compliance_promotion_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION planogram_plan_lifecycle_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE dna_status varchar(20); dna_geometry boolean; dna_store varchar(80);
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.store_dna_version_id IS DISTINCT FROM OLD.store_dna_version_id
               OR NEW.store_code IS DISTINCT FROM OLD.store_code
               OR NEW.version_number IS DISTINCT FROM OLD.version_number
               OR NEW.source IS DISTINCT FROM OLD.source
               OR NEW.created_by IS DISTINCT FROM OLD.created_by
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION 'Planogram plan identity is immutable';
            END IF;

            IF OLD.status = 'draft' THEN
                IF NEW.status NOT IN ('draft','submitted') THEN
                    RAISE EXCEPTION 'Planogram draft may only remain draft or become submitted';
                END IF;
            ELSIF OLD.status = 'submitted' THEN
                IF NEW.status NOT IN ('submitted','approved','rejected') THEN
                    RAISE EXCEPTION 'Invalid submitted Planogram transition';
                END IF;
                IF NEW.plan_payload IS DISTINCT FROM OLD.plan_payload
                   OR NEW.plan_fingerprint IS DISTINCT FROM OLD.plan_fingerprint
                   OR NEW.optimizer_fingerprint IS DISTINCT FROM OLD.optimizer_fingerprint
                THEN
                    RAISE EXCEPTION 'Submitted Planogram candidate payload is immutable';
                END IF;
            ELSIF OLD.status = 'approved' THEN
                IF NEW.status <> 'superseded'
                   OR NEW.plan_payload IS DISTINCT FROM OLD.plan_payload
                   OR NEW.plan_fingerprint IS DISTINCT FROM OLD.plan_fingerprint
                   OR NEW.optimizer_fingerprint IS DISTINCT FROM OLD.optimizer_fingerprint
                   OR NEW.physical_truth_attested IS DISTINCT FROM OLD.physical_truth_attested
                   OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by
                   OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at
                   OR NEW.approved_by IS DISTINCT FROM OLD.approved_by
                   OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
                   OR NEW.rejected_by IS DISTINCT FROM OLD.rejected_by
                   OR NEW.rejected_at IS DISTINCT FROM OLD.rejected_at
                   OR NEW.rejection_reason IS DISTINCT FROM OLD.rejection_reason
                THEN
    RAISE EXCEPTION 'Approved Planogram plan is immutable except approved -> superseded';
                END IF;
            ELSIF OLD.status IN ('rejected','superseded') THEN
                RAISE EXCEPTION 'Terminal Planogram plan version is immutable';
            END IF;

            IF NEW.status = 'approved' AND OLD.status = 'submitted' THEN
                IF NOT NEW.physical_truth_attested THEN
    RAISE EXCEPTION 'Planogram approval requires external physical-truth attestation';
                END IF;
                IF NEW.submitted_by IS NULL OR NEW.approved_by IS NULL
                   OR NEW.submitted_by = NEW.approved_by
                THEN
                    RAISE EXCEPTION 'Planogram approval requires maker-checker separation';
                END IF;
                SELECT status, geometry_attested, store_code
                INTO dna_status, dna_geometry, dna_store
                FROM planogram_store_dna_versions
                WHERE tenant_id=NEW.tenant_id AND id=NEW.store_dna_version_id;
                IF dna_status IS DISTINCT FROM 'approved'
                   OR NOT COALESCE(dna_geometry, FALSE)
                   OR dna_store IS DISTINCT FROM NEW.store_code
                THEN
    RAISE EXCEPTION 'Planogram approval requires approved attested Store DNA for the same store';
                END IF;
            END IF;
            RETURN NEW;
        END; $$
        """)


def downgrade() -> None:
    # Security hardening is intentionally non-reversible without replacing the
    # previous migration chain. Downgrade preserves the hardened function.
    pass
