"""Master 31 workstream: Academy skill graph and proficiency authority.

Isolated workstream revision; migration ancestry is rebased before canonical composition.
Revision ID: 0040_academy_learning_os
Revises: 0036_planogram_product_roles
"""
from collections.abc import Sequence
from alembic import op

revision: str = "0040_academy_learning_os"
down_revision: str | None = "0036_planogram_product_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
RUNTIME_ROLE="opex_runtime"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE academy_skills(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      skill_key varchar(160) NOT NULL, title_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
      description_i18n jsonb NOT NULL DEFAULT '{}'::jsonb, status varchar(20) NOT NULL DEFAULT 'active',
      created_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      CHECK(status IN ('active','retired')), UNIQUE(tenant_id,skill_key), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE TABLE academy_role_skill_requirement(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, role_key varchar(160) NOT NULL,
      skill_id uuid NOT NULL, required_level smallint NOT NULL, source varchar(255) NOT NULL,
      effective_from date NOT NULL DEFAULT CURRENT_DATE, effective_to date,
      created_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,skill_id) REFERENCES academy_skills(tenant_id,id) ON DELETE RESTRICT,
      CHECK(required_level BETWEEN 1 AND 5), CHECK(effective_to IS NULL OR effective_to>=effective_from),
      UNIQUE(tenant_id,role_key,skill_id,effective_from), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE TABLE academy_path_skill_outcome(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, path_id uuid NOT NULL,
      skill_id uuid NOT NULL, target_level smallint NOT NULL, created_by varchar(255) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,path_id) REFERENCES academy_learning_paths(tenant_id,id) ON DELETE CASCADE,
      FOREIGN KEY(tenant_id,skill_id) REFERENCES academy_skills(tenant_id,id) ON DELETE RESTRICT,
      CHECK(target_level BETWEEN 1 AND 5), UNIQUE(tenant_id,path_id,skill_id), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE TABLE academy_skill_evidence(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, subject varchar(255) NOT NULL,
      skill_id uuid NOT NULL, observed_level smallint NOT NULL, evidence_type varchar(30) NOT NULL,
      evidence_ref varchar(255) NOT NULL, observed_at timestamptz NOT NULL DEFAULT now(),
      recorded_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,skill_id) REFERENCES academy_skills(tenant_id,id) ON DELETE RESTRICT,
      CHECK(observed_level BETWEEN 0 AND 5),
      CHECK(evidence_type IN ('assessment','certificate','manager_verified','external_verified')),
      UNIQUE(tenant_id,subject,skill_id,evidence_type,evidence_ref), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE VIEW academy_subject_skill_proficiency WITH (security_invoker = true) AS
    SELECT DISTINCT ON (tenant_id,subject,skill_id)
      tenant_id,subject,skill_id,observed_level,evidence_type,evidence_ref,observed_at
    FROM academy_skill_evidence
    ORDER BY tenant_id,subject,skill_id,observed_at DESC,id DESC
    """)
    for table in ('academy_skills','academy_role_skill_requirement','academy_path_skill_outcome','academy_skill_evidence'):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid)")
    op.execute(f"GRANT SELECT ON academy_skills,academy_role_skill_requirement,academy_path_skill_outcome,academy_skill_evidence,academy_subject_skill_proficiency TO {RUNTIME_ROLE}")
    op.execute(f"GRANT INSERT ON academy_skill_evidence TO {RUNTIME_ROLE}")
    op.execute(f"REVOKE UPDATE,DELETE ON academy_skill_evidence FROM {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute('DROP VIEW IF EXISTS academy_subject_skill_proficiency')
    for table in ('academy_skill_evidence','academy_path_skill_outcome','academy_role_skill_requirement','academy_skills'):
        op.execute(f'DROP TABLE IF EXISTS {table}')
