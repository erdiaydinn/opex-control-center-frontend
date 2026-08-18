"""Master 30: finance-grade export/import/UAT controls.
Revision ID: 0039_budget_finance_controls
Revises: 0038_budget_ai_recommendation_authority
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0039_budget_finance_controls"
down_revision: str | None = "0038_budget_ai_recommendation_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
RUNTIME = "opex_runtime"


def upgrade() -> None:
    op.execute("""CREATE TABLE budget_export_request(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, requested_by varchar(255) NOT NULL,
      export_type varchar(80) NOT NULL, filters jsonb NOT NULL, status varchar(20) NOT NULL DEFAULT 'PENDING',
      decided_by varchar(255), output_sha256 char(64), created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz,
      CHECK(status IN ('PENDING','APPROVED','REJECTED','EXPORTED')), UNIQUE(tenant_id,id))""")
    op.execute("""CREATE TABLE budget_import_version(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, import_batch_id uuid NOT NULL,
      source_sha256 char(64) NOT NULL, schema_version varchar(80) NOT NULL, mapping_version varchar(80) NOT NULL,
      validation_summary jsonb NOT NULL, created_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,import_batch_id) REFERENCES import_batch(tenant_id,id) ON DELETE RESTRICT,
      CHECK(source_sha256 ~ '^[0-9a-f]{64}$'), UNIQUE(tenant_id,source_sha256,schema_version,mapping_version), UNIQUE(tenant_id,id))""")
    op.execute("""CREATE TABLE budget_finance_uat_attestation(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, evidence_ref varchar(500) NOT NULL,
      environment varchar(120) NOT NULL, reconciliation_ref varchar(500) NOT NULL,
      status varchar(20) NOT NULL, approved_by varchar(255) NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
      CHECK(status IN ('PASS','FAIL')), CHECK(environment NOT IN ('ci','repository','synthetic')), UNIQUE(tenant_id,evidence_ref), UNIQUE(tenant_id,id))""")
    for t in ("budget_export_request", "budget_import_version", "budget_finance_uat_attestation"):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {t}_tenant ON {t} USING (budget_tenant_allows(tenant_id)) WITH CHECK (budget_tenant_allows(tenant_id))")
    op.execute("""CREATE OR REPLACE FUNCTION budget_export_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.status='PENDING' AND NEW.status IN ('APPROVED','REJECTED') AND (NEW.decided_by IS NULL OR NEW.decided_by=OLD.requested_by) THEN RAISE EXCEPTION 'independent export decision required'; END IF;
      IF OLD.status='APPROVED' AND NEW.status='EXPORTED' AND NEW.output_sha256 !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'export output hash required'; END IF;
      IF NOT ((OLD.status='PENDING' AND NEW.status IN ('APPROVED','REJECTED')) OR (OLD.status='APPROVED' AND NEW.status='EXPORTED') OR OLD.status=NEW.status) THEN RAISE EXCEPTION 'invalid export lifecycle'; END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER trg_budget_export_guard BEFORE UPDATE ON budget_export_request FOR EACH ROW EXECUTE FUNCTION budget_export_guard()")
    op.execute(f"GRANT SELECT,INSERT ON budget_export_request,budget_import_version TO {RUNTIME}")
    op.execute(f"GRANT UPDATE(status,decided_by,decided_at,output_sha256) ON budget_export_request TO {RUNTIME}")
    op.execute(f"GRANT SELECT ON budget_finance_uat_attestation TO {RUNTIME}")
    op.execute(f"REVOKE INSERT,UPDATE,DELETE ON budget_finance_uat_attestation FROM {RUNTIME}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_budget_export_guard ON budget_export_request")
    op.execute("DROP FUNCTION IF EXISTS budget_export_guard()")
    for t in ("budget_finance_uat_attestation", "budget_import_version", "budget_export_request"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
