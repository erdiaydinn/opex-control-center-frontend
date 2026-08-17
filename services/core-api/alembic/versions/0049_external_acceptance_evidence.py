"""Master 49-55 isolated external acceptance evidence ledger.

Revision ID: 0049_external_acceptance_evidence
Revises: 0036_planogram_product_roles
Migration ancestry is rebased before canonical composition.
"""
from collections.abc import Sequence
from alembic import op
revision: str='0049_external_acceptance_evidence'
down_revision: str|None='0036_planogram_product_roles'
branch_labels: str|Sequence[str]|None=None
depends_on: str|Sequence[str]|None=None
RUNTIME='opex_runtime'

def upgrade()->None:
    op.execute("""CREATE TABLE external_acceptance_evidence(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
      roadmap_item smallint NOT NULL, requirement_key varchar(160) NOT NULL,
      evidence_key varchar(160) NOT NULL, evidence_class varchar(40) NOT NULL,
      status varchar(20) NOT NULL, environment varchar(160) NOT NULL,
      provenance varchar(1000) NOT NULL, approver varchar(255) NOT NULL,
      observed_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      CHECK(roadmap_item BETWEEN 49 AND 55),
      CHECK(evidence_class IN ('MANAGED_STAGING','REAL_STAGING','REAL_ENVIRONMENT','REAL_BUILD_UAT')),
      CHECK(status IN ('PASS','FAIL')),
      CHECK(length(trim(environment))>0 AND length(trim(provenance))>0 AND length(trim(approver))>0),
      UNIQUE(tenant_id,roadmap_item,requirement_key,evidence_key,observed_at), UNIQUE(tenant_id,id))""")
    op.execute("ALTER TABLE external_acceptance_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE external_acceptance_evidence FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY external_acceptance_evidence_tenant ON external_acceptance_evidence USING (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid)")
    op.execute("""CREATE OR REPLACE FUNCTION external_acceptance_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'external acceptance evidence is append-only'; END $$""")
    op.execute("CREATE TRIGGER trg_external_acceptance_immutable BEFORE UPDATE OR DELETE ON external_acceptance_evidence FOR EACH ROW EXECUTE FUNCTION external_acceptance_evidence_immutable()")
    op.execute(f'GRANT SELECT ON external_acceptance_evidence TO {RUNTIME}')
    op.execute(f'REVOKE INSERT,UPDATE,DELETE ON external_acceptance_evidence FROM {RUNTIME}')

def downgrade()->None:
    op.execute('DROP TRIGGER IF EXISTS trg_external_acceptance_immutable ON external_acceptance_evidence')
    op.execute('DROP FUNCTION IF EXISTS external_acceptance_evidence_immutable()')
    op.execute('DROP TABLE IF EXISTS external_acceptance_evidence')
