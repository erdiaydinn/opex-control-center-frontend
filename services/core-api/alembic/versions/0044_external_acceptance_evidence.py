"""Master 49-55 external acceptance evidence ledger.

Revision ID: 0044_external_acceptance_evidence
Revises: 0043_shared_platform_delivery_search
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0044_external_acceptance_evidence"
down_revision: str | None = "0043_shared_platform_delivery_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME = "opex_runtime"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE external_acceptance_evidence (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          release_id varchar(160) NOT NULL,
          candidate_sha char(40) NOT NULL,
          roadmap_item smallint NOT NULL,
          requirement_key varchar(160) NOT NULL,
          evidence_key varchar(160) NOT NULL,
          evidence_class varchar(40) NOT NULL,
          status varchar(20) NOT NULL,
          environment varchar(160) NOT NULL,
          provenance varchar(1000) NOT NULL,
          artifact_sha256 char(64) NOT NULL,
          approver varchar(255) NOT NULL,
          observed_at timestamptz NOT NULL,
          expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (roadmap_item BETWEEN 49 AND 55),
          CHECK (length(trim(release_id)) > 0),
          CHECK (candidate_sha ~ '^[0-9a-f]{40}$'),
          CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
          CHECK (expires_at > observed_at),
          CHECK (
            evidence_class IN (
              'MANAGED_STAGING',
              'REAL_STAGING',
              'REAL_ENVIRONMENT',
              'REAL_BUILD_UAT'
            )
          ),
          CHECK (status IN ('PASS', 'FAIL', 'REVOKED')),
          CHECK (length(trim(environment)) > 0),
          CHECK (length(trim(provenance)) > 0),
          CHECK (length(trim(approver)) > 0),
          UNIQUE (
            tenant_id,
            release_id,
            candidate_sha,
            roadmap_item,
            requirement_key,
            evidence_key,
            observed_at
          ),
          UNIQUE (tenant_id, id)
        )"""
    )
    op.execute(
        """CREATE INDEX external_acceptance_evidence_latest_idx
        ON external_acceptance_evidence (
          tenant_id,
          release_id,
          candidate_sha,
          roadmap_item,
          requirement_key,
          evidence_key,
          observed_at DESC
        )"""
    )
    op.execute("ALTER TABLE external_acceptance_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE external_acceptance_evidence FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY external_acceptance_evidence_tenant
        ON external_acceptance_evidence
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )"""
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION external_acceptance_evidence_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'external acceptance evidence is append-only';
        END
        $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_external_acceptance_immutable
        BEFORE UPDATE OR DELETE ON external_acceptance_evidence
        FOR EACH ROW EXECUTE FUNCTION external_acceptance_evidence_immutable()"""
    )
    op.execute(f"GRANT SELECT ON external_acceptance_evidence TO {RUNTIME}")
    op.execute(
        f"REVOKE INSERT, UPDATE, DELETE ON external_acceptance_evidence FROM {RUNTIME}"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_external_acceptance_immutable "
        "ON external_acceptance_evidence"
    )
    op.execute("DROP FUNCTION IF EXISTS external_acceptance_evidence_immutable()")
    op.execute("DROP INDEX IF EXISTS external_acceptance_evidence_latest_idx")
    op.execute("DROP TABLE IF EXISTS external_acceptance_evidence")
