"""Add immutable Budget planning authority and exact forecast scope.

Revision ID: 0037_budget_planning_authority
Revises: 0036_planogram_product_roles
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037_budget_planning_authority"
down_revision: str = "0036_planogram_product_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVATION_TRIGGER = "ACTIVATION_TRIGGER"
LEGACY_RECONSTRUCTION = "LEGACY_MIGRATION_RECONSTRUCTION"


def upgrade() -> None:
    # Never repair finance truth silently. Existing inconsistencies must be
    # reconciled explicitly before this authority can be promoted.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM budget_line l
            JOIN fiscal_period p
              ON p.tenant_id=l.tenant_id AND p.id=l.fiscal_period_id
            WHERE p.plan_id <> l.plan_id
          ) THEN
            RAISE EXCEPTION 'Budget Line / Fiscal Period plan-scope inconsistency exists';
          END IF;

          IF EXISTS (
            SELECT 1
            FROM forecast f
            JOIN budget_line l
              ON l.tenant_id=f.tenant_id AND l.id=f.budget_line_id
            WHERE l.fiscal_period_id <> f.fiscal_period_id
               OR l.cost_center_id <> f.cost_center_id
          ) THEN
            RAISE EXCEPTION 'Forecast / Budget Line scope inconsistency exists';
          END IF;
        END $$;
        """
    )

    op.execute(
        """
        ALTER TABLE fiscal_period
          ADD CONSTRAINT uq_fiscal_period_plan_scope
          UNIQUE (tenant_id,id,plan_id)
        """
    )
    op.execute(
        """
        ALTER TABLE budget_line
          ADD CONSTRAINT fk_budget_line_exact_plan_period
          FOREIGN KEY (tenant_id,fiscal_period_id,plan_id)
          REFERENCES fiscal_period(tenant_id,id,plan_id)
          ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        ALTER TABLE forecast
          ADD CONSTRAINT fk_budget_forecast_exact_line_scope
          FOREIGN KEY (tenant_id,budget_line_id,fiscal_period_id,cost_center_id)
          REFERENCES budget_line(tenant_id,id,fiscal_period_id,cost_center_id)
          ON DELETE RESTRICT
        """
    )

    op.execute(
        """
        ALTER TABLE budget_plan
          ADD COLUMN planning_snapshot jsonb,
          ADD COLUMN planning_fingerprint char(64),
          ADD COLUMN planning_snapshot_at timestamptz,
          ADD COLUMN planning_snapshot_provenance varchar(40)
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_plan_planning_snapshot(
          p_tenant uuid,
          p_plan uuid
        )
        RETURNS jsonb
        LANGUAGE sql
        STABLE
        AS $$
          SELECT jsonb_build_object(
            'schema_version', 1,
            'plan', jsonb_build_object(
              'id', b.id,
              'name', b.name,
              'fiscal_year', b.fiscal_year,
              'base_currency', b.base_currency
            ),
            'periods', COALESCE((
              SELECT jsonb_agg(
                jsonb_build_object(
                  'id', p.id,
                  'code', p.code,
                  'starts_on', p.starts_on,
                  'ends_on', p.ends_on
                )
                ORDER BY p.starts_on,p.ends_on,p.code,p.id
              )
              FROM fiscal_period p
              WHERE p.tenant_id=b.tenant_id AND p.plan_id=b.id
            ), '[]'::jsonb),
            'lines', COALESCE((
              SELECT jsonb_agg(
                jsonb_build_object(
                  'id', l.id,
                  'fiscal_period_id', l.fiscal_period_id,
                  'cost_center_id', l.cost_center_id,
                  'cost_center_code', c.code,
                  'cost_center_name', c.name,
                  'cost_center_store_code', c.store_code,
                  'category', l.category,
                  'supplier_id', l.supplier_id,
                  'supplier_name', l.supplier_name,
                  'store_code', l.store_code,
                  'budget_base_amount', l.budget_base_amount
                )
                ORDER BY p.starts_on,p.code,c.code,l.category,l.id
              )
              FROM budget_line l
              JOIN fiscal_period p
                ON p.tenant_id=l.tenant_id
               AND p.id=l.fiscal_period_id
               AND p.plan_id=l.plan_id
              JOIN cost_center c
                ON c.tenant_id=l.tenant_id AND c.id=l.cost_center_id
              WHERE l.tenant_id=b.tenant_id AND l.plan_id=b.id
            ), '[]'::jsonb)
          )
          FROM budget_plan b
          WHERE b.tenant_id=p_tenant AND b.id=p_plan
        $$;
        """
    )

    # Pre-existing ACTIVE plans did not have an activation-time snapshot. We do
    # capture their current exact structure so they can be protected going
    # forward, but we label it explicitly as a migration-time reconstruction and
    # timestamp the observation NOW. This must never be presented as historical
    # activation evidence.
    op.execute(
        f"""
        UPDATE budget_plan b
        SET planning_snapshot = budget_plan_planning_snapshot(b.tenant_id,b.id),
            planning_fingerprint = encode(
              digest(
                convert_to(
                  budget_plan_planning_snapshot(b.tenant_id,b.id)::text,
                  'UTF8'
                ),
                'sha256'
              ),
              'hex'
            ),
            planning_snapshot_at = CURRENT_TIMESTAMP,
            planning_snapshot_provenance = '{LEGACY_RECONSTRUCTION}'
        WHERE b.status='ACTIVE'
        """
    )

    op.execute(
        f"""
        ALTER TABLE budget_plan
          ADD CONSTRAINT ck_budget_plan_planning_authority
          CHECK (
            (
              status='DRAFT'
              AND planning_snapshot IS NULL
              AND planning_fingerprint IS NULL
              AND planning_snapshot_at IS NULL
              AND planning_snapshot_provenance IS NULL
            )
            OR
            (
              status='ACTIVE'
              AND planning_snapshot IS NOT NULL
              AND planning_fingerprint ~ '^[0-9a-f]{{64}}$'
              AND planning_snapshot_at IS NOT NULL
              AND planning_snapshot_provenance IN (
                '{ACTIVATION_TRIGGER}',
                '{LEGACY_RECONSTRUCTION}'
              )
            )
          )
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION budget_plan_planning_authority_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          period_count integer;
          line_count integer;
          snapshot jsonb;
        BEGIN
          IF TG_OP='INSERT' THEN
            IF NEW.status <> 'DRAFT'
               OR NEW.activated_by IS NOT NULL
               OR NEW.activated_at IS NOT NULL
               OR NEW.planning_snapshot IS NOT NULL
               OR NEW.planning_fingerprint IS NOT NULL
               OR NEW.planning_snapshot_at IS NOT NULL
               OR NEW.planning_snapshot_provenance IS NOT NULL
            THEN
              RAISE EXCEPTION 'Budget Plan must begin as an unactivated DRAFT';
            END IF;
            RETURN NEW;
          END IF;

          IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
             OR NEW.id IS DISTINCT FROM OLD.id
             OR NEW.created_by IS DISTINCT FROM OLD.created_by
             OR NEW.created_at IS DISTINCT FROM OLD.created_at
          THEN
            RAISE EXCEPTION 'Budget Plan identity is immutable';
          END IF;

          IF OLD.status='ACTIVE' THEN
            RAISE EXCEPTION 'ACTIVE Budget Plan and activation snapshot are immutable';
          END IF;

          IF NEW.status='DRAFT' THEN
            IF NEW.activated_by IS NOT NULL
               OR NEW.activated_at IS NOT NULL
               OR NEW.planning_snapshot IS NOT NULL
               OR NEW.planning_fingerprint IS NOT NULL
               OR NEW.planning_snapshot_at IS NOT NULL
               OR NEW.planning_snapshot_provenance IS NOT NULL
            THEN
              RAISE EXCEPTION 'DRAFT Budget Plan cannot carry activation evidence';
            END IF;
            RETURN NEW;
          END IF;

          IF OLD.status='DRAFT' AND NEW.status='ACTIVE' THEN
            IF NEW.activated_by IS NULL
               OR NEW.activated_at IS NULL
               OR NEW.activated_by = NEW.created_by
            THEN
              RAISE EXCEPTION 'Budget Plan activation requires maker-checker separation';
            END IF;
            IF NEW.planning_snapshot IS NOT NULL
               OR NEW.planning_fingerprint IS NOT NULL
               OR NEW.planning_snapshot_at IS NOT NULL
               OR NEW.planning_snapshot_provenance IS NOT NULL
            THEN
              RAISE EXCEPTION 'Budget activation evidence is server-authored';
            END IF;

            SELECT COUNT(*) INTO period_count
            FROM fiscal_period
            WHERE tenant_id=NEW.tenant_id AND plan_id=NEW.id;
            SELECT COUNT(*) INTO line_count
            FROM budget_line
            WHERE tenant_id=NEW.tenant_id AND plan_id=NEW.id;
            IF period_count < 1 OR line_count < 1 THEN
              RAISE EXCEPTION 'Budget Plan activation requires Fiscal Period and Budget Line';
            END IF;

            snapshot := budget_plan_planning_snapshot(NEW.tenant_id,NEW.id);
            NEW.planning_snapshot := snapshot;
            NEW.planning_fingerprint := encode(
              digest(convert_to(snapshot::text,'UTF8'),'sha256'),
              'hex'
            );
            NEW.planning_snapshot_at := NEW.activated_at;
            NEW.planning_snapshot_provenance := '{ACTIVATION_TRIGGER}';
            RETURN NEW;
          END IF;

          RAISE EXCEPTION 'Invalid Budget Plan lifecycle transition';
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_budget_plan_planning_authority
        BEFORE INSERT OR UPDATE ON budget_plan
        FOR EACH ROW EXECUTE FUNCTION budget_plan_planning_authority_guard()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_line_draft_plan_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          target_tenant uuid;
          target_plan uuid;
          plan_status varchar(20);
        BEGIN
          IF TG_OP='DELETE' THEN
            target_tenant := OLD.tenant_id;
            target_plan := OLD.plan_id;
          ELSE
            target_tenant := NEW.tenant_id;
            target_plan := NEW.plan_id;
          END IF;

          IF TG_OP='UPDATE' AND (
            NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
            OR NEW.id IS DISTINCT FROM OLD.id
            OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
            OR NEW.created_by IS DISTINCT FROM OLD.created_by
            OR NEW.created_at IS DISTINCT FROM OLD.created_at
          ) THEN
            RAISE EXCEPTION 'Budget Line identity is immutable';
          END IF;

          SELECT status INTO plan_status
          FROM budget_plan
          WHERE tenant_id=target_tenant AND id=target_plan
          FOR SHARE;

          IF plan_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'Budget Line structure requires DRAFT Budget Plan';
          END IF;

          RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_budget_line_draft_plan
        BEFORE INSERT OR UPDATE OR DELETE ON budget_line
        FOR EACH ROW EXECUTE FUNCTION budget_line_draft_plan_guard()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fiscal_period_plan_structure_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          target_tenant uuid;
          target_plan uuid;
          plan_status varchar(20);
          structural_change boolean := false;
        BEGIN
          IF TG_OP='DELETE' THEN
            target_tenant := OLD.tenant_id;
            target_plan := OLD.plan_id;
            structural_change := true;
          ELSE
            target_tenant := NEW.tenant_id;
            target_plan := NEW.plan_id;
          END IF;

          IF TG_OP='UPDATE' THEN
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.id IS DISTINCT FROM OLD.id
               OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
            THEN
              RAISE EXCEPTION 'Fiscal Period identity is immutable';
            END IF;

            structural_change :=
              NEW.code IS DISTINCT FROM OLD.code
              OR NEW.starts_on IS DISTINCT FROM OLD.starts_on
              OR NEW.ends_on IS DISTINCT FROM OLD.ends_on;

            IF NEW.status IS DISTINCT FROM OLD.status THEN
              IF OLD.status <> 'OPEN'
                 OR NEW.status <> 'CLOSED'
                 OR NEW.closed_by IS NULL
                 OR NEW.closed_at IS NULL
              THEN
                RAISE EXCEPTION 'Fiscal Period only supports OPEN -> CLOSED';
              END IF;
            ELSIF NEW.closed_by IS DISTINCT FROM OLD.closed_by
               OR NEW.closed_at IS DISTINCT FROM OLD.closed_at
            THEN
              RAISE EXCEPTION 'Fiscal Period close evidence is immutable';
            END IF;
          ELSIF TG_OP='INSERT' THEN
            structural_change := true;
          END IF;

          IF structural_change THEN
            SELECT status INTO plan_status
            FROM budget_plan
            WHERE tenant_id=target_tenant AND id=target_plan
            FOR SHARE;
            IF plan_status IS DISTINCT FROM 'DRAFT' THEN
              RAISE EXCEPTION 'Fiscal Period structure requires DRAFT Budget Plan';
            END IF;
          END IF;

          RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_fiscal_period_plan_structure
        BEFORE INSERT OR UPDATE OR DELETE ON fiscal_period
        FOR EACH ROW EXECUTE FUNCTION fiscal_period_plan_structure_guard()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_fiscal_period_plan_structure ON fiscal_period")
    op.execute("DROP FUNCTION IF EXISTS fiscal_period_plan_structure_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_budget_line_draft_plan ON budget_line")
    op.execute("DROP FUNCTION IF EXISTS budget_line_draft_plan_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_budget_plan_planning_authority ON budget_plan")
    op.execute("DROP FUNCTION IF EXISTS budget_plan_planning_authority_guard()")
    op.execute("ALTER TABLE budget_plan DROP CONSTRAINT IF EXISTS ck_budget_plan_planning_authority")
    op.execute(
        "ALTER TABLE budget_plan "
        "DROP COLUMN IF EXISTS planning_snapshot_provenance,"
        "DROP COLUMN IF EXISTS planning_snapshot_at,"
        "DROP COLUMN IF EXISTS planning_fingerprint,"
        "DROP COLUMN IF EXISTS planning_snapshot"
    )
    op.execute("DROP FUNCTION IF EXISTS budget_plan_planning_snapshot(uuid,uuid)")
    op.execute("ALTER TABLE forecast DROP CONSTRAINT IF EXISTS fk_budget_forecast_exact_line_scope")
    op.execute("ALTER TABLE budget_line DROP CONSTRAINT IF EXISTS fk_budget_line_exact_plan_period")
    op.execute("ALTER TABLE fiscal_period DROP CONSTRAINT IF EXISTS uq_fiscal_period_plan_scope")
