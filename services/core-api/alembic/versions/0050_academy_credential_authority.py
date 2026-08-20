"""Add evidence-bound Academy badge and credential authority.

Revision ID: 0050_academy_credential_authority
Revises: 0049_academy_localization_governance
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050_academy_credential_authority"
down_revision: str | None = "0049_academy_localization_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
CREDENTIAL_TABLES = (
    "academy_badge_definitions",
    "academy_badge_definition_retirements",
    "academy_badge_awards",
    "academy_badge_revocations",
)


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''
        CREATE POLICY "{table_name}_tenant_isolation"
        ON "{table_name}"
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        '''
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE academy_badge_definitions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            badge_key varchar(160) NOT NULL,
            version_number integer NOT NULL,
            skill_id uuid NOT NULL,
            minimum_level smallint NOT NULL,
            title_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            description_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            criteria_i18n jsonb NOT NULL DEFAULT '{}'::jsonb,
            validity_days integer,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_badge_definition_skill
                FOREIGN KEY (tenant_id, skill_id)
                REFERENCES academy_skills(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_academy_badge_definition_version
                CHECK (version_number >= 1),
            CONSTRAINT ck_academy_badge_definition_level
                CHECK (minimum_level BETWEEN 1 AND 5),
            CONSTRAINT ck_academy_badge_definition_validity
                CHECK (validity_days IS NULL OR validity_days BETWEEN 1 AND 3650),
            CONSTRAINT uq_academy_badge_definition_version
                UNIQUE (tenant_id, badge_key, version_number),
            CONSTRAINT uq_academy_badge_definition_tenant_id
                UNIQUE (tenant_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE academy_badge_definition_retirements (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            badge_definition_id uuid NOT NULL,
            reason text NOT NULL,
            retired_by varchar(255) NOT NULL,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_badge_retirement_definition
                FOREIGN KEY (tenant_id, badge_definition_id)
                REFERENCES academy_badge_definitions(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_academy_badge_retirement_reason
                CHECK (NULLIF(btrim(reason), '') IS NOT NULL),
            CONSTRAINT uq_academy_badge_definition_retired
                UNIQUE (tenant_id, badge_definition_id),
            CONSTRAINT uq_academy_badge_retirement_request
                UNIQUE (tenant_id, request_id),
            CONSTRAINT uq_academy_badge_retirement_tenant_id
                UNIQUE (tenant_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE academy_badge_awards (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            badge_definition_id uuid NOT NULL,
            skill_evidence_id uuid NOT NULL,
            subject varchar(255) NOT NULL,
            skill_id uuid NOT NULL,
            observed_level smallint NOT NULL,
            evidence_type varchar(30) NOT NULL,
            evidence_ref varchar(255) NOT NULL,
            issuer_subject varchar(255) NOT NULL,
            issued_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at timestamptz,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_badge_award_definition
                FOREIGN KEY (tenant_id, badge_definition_id)
                REFERENCES academy_badge_definitions(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_academy_badge_award_evidence
                FOREIGN KEY (tenant_id, skill_evidence_id)
                REFERENCES academy_skill_evidence(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_academy_badge_award_skill
                FOREIGN KEY (tenant_id, skill_id)
                REFERENCES academy_skills(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_academy_badge_award_level
                CHECK (observed_level BETWEEN 1 AND 5),
            CONSTRAINT ck_academy_badge_award_expiry
                CHECK (expires_at IS NULL OR expires_at > issued_at),
            CONSTRAINT uq_academy_badge_award_evidence
                UNIQUE (tenant_id, badge_definition_id, skill_evidence_id),
            CONSTRAINT uq_academy_badge_award_request
                UNIQUE (tenant_id, request_id),
            CONSTRAINT uq_academy_badge_award_tenant_id
                UNIQUE (tenant_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE academy_badge_revocations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            badge_award_id uuid NOT NULL,
            reason text NOT NULL,
            revoked_by varchar(255) NOT NULL,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_badge_revocation_award
                FOREIGN KEY (tenant_id, badge_award_id)
                REFERENCES academy_badge_awards(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_academy_badge_revocation_reason
                CHECK (NULLIF(btrim(reason), '') IS NOT NULL),
            CONSTRAINT uq_academy_badge_award_revoked
                UNIQUE (tenant_id, badge_award_id),
            CONSTRAINT uq_academy_badge_revocation_request
                UNIQUE (tenant_id, request_id),
            CONSTRAINT uq_academy_badge_revocation_tenant_id
                UNIQUE (tenant_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION academy_validate_badge_award()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        DECLARE
            required_skill uuid;
            required_level smallint;
            validity integer;
            retired boolean;
            evidence_subject varchar(255);
            evidence_skill uuid;
            evidence_level smallint;
            evidence_kind varchar(30);
            evidence_reference varchar(255);
            skill_status varchar(20);
        BEGIN
            SELECT
                definition.skill_id,
                definition.minimum_level,
                definition.validity_days,
                EXISTS (
                    SELECT 1
                    FROM academy_badge_definition_retirements AS retirement
                    WHERE retirement.tenant_id = definition.tenant_id
                      AND retirement.badge_definition_id = definition.id
                )
            INTO required_skill, required_level, validity, retired
            FROM academy_badge_definitions AS definition
            WHERE definition.tenant_id = NEW.tenant_id
              AND definition.id = NEW.badge_definition_id;

            IF required_skill IS NULL THEN
                RAISE EXCEPTION 'Academy badge definition not found';
            END IF;
            IF retired THEN
                RAISE EXCEPTION 'Academy badge definition is retired';
            END IF;

            SELECT
                evidence.subject,
                evidence.skill_id,
                evidence.observed_level,
                evidence.evidence_type,
                evidence.evidence_ref
            INTO
                evidence_subject,
                evidence_skill,
                evidence_level,
                evidence_kind,
                evidence_reference
            FROM academy_skill_evidence AS evidence
            WHERE evidence.tenant_id = NEW.tenant_id
              AND evidence.id = NEW.skill_evidence_id;

            IF evidence_subject IS NULL THEN
                RAISE EXCEPTION 'Academy skill evidence not found';
            END IF;
            IF evidence_skill <> required_skill THEN
                RAISE EXCEPTION 'Badge skill does not match skill evidence';
            END IF;
            IF evidence_level < required_level THEN
                RAISE EXCEPTION 'Skill evidence does not satisfy badge level';
            END IF;

            SELECT status
            INTO skill_status
            FROM academy_skills
            WHERE tenant_id = NEW.tenant_id
              AND id = required_skill;
            IF skill_status IS DISTINCT FROM 'active' THEN
                RAISE EXCEPTION 'Retired skill cannot issue new badge awards';
            END IF;

            NEW.subject := evidence_subject;
            NEW.skill_id := evidence_skill;
            NEW.observed_level := evidence_level;
            NEW.evidence_type := evidence_kind;
            NEW.evidence_ref := evidence_reference;
            IF validity IS NULL THEN
                NEW.expires_at := NULL;
            ELSE
                NEW.expires_at := NEW.issued_at + make_interval(days => validity);
            END IF;
            RETURN NEW;
        END;
        $body$
        """
    )
    op.execute(
        """
        CREATE TRIGGER academy_badge_award_evidence_guard
        BEFORE INSERT ON academy_badge_awards
        FOR EACH ROW
        EXECUTE FUNCTION academy_validate_badge_award()
        """
    )

    op.execute(
        """
        CREATE FUNCTION academy_prevent_credential_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        BEGIN
            RAISE EXCEPTION 'Academy credential evidence is append-only';
        END;
        $body$
        """
    )
    for table_name in CREDENTIAL_TABLES:
        op.execute(
            f'''
            CREATE TRIGGER "{table_name}_append_only"
            BEFORE UPDATE OR DELETE ON "{table_name}"
            FOR EACH ROW
            EXECUTE FUNCTION academy_prevent_credential_mutation()
            '''
        )

    op.execute(
        """
        CREATE VIEW academy_badge_definition_authority
        WITH (security_invoker = true) AS
        SELECT
            definition.tenant_id,
            definition.id AS badge_definition_id,
            definition.badge_key,
            definition.version_number,
            definition.skill_id,
            definition.minimum_level,
            definition.title_i18n,
            definition.description_i18n,
            definition.criteria_i18n,
            definition.validity_days,
            definition.created_by,
            definition.created_at,
            retirement.created_at AS retired_at,
            retirement.retired_by,
            retirement.reason AS retirement_reason,
            (retirement.id IS NULL) AS issuable
        FROM academy_badge_definitions AS definition
        LEFT JOIN academy_badge_definition_retirements AS retirement
          ON retirement.tenant_id = definition.tenant_id
         AND retirement.badge_definition_id = definition.id
        """
    )

    op.execute(
        """
        CREATE VIEW academy_badge_credential_authority
        WITH (security_invoker = true) AS
        SELECT
            award.tenant_id,
            award.id AS badge_award_id,
            award.badge_definition_id,
            definition.badge_key,
            definition.version_number AS badge_version,
            definition.title_i18n,
            definition.description_i18n,
            definition.criteria_i18n,
            award.subject,
            award.skill_id,
            award.observed_level,
            award.skill_evidence_id,
            award.evidence_type,
            award.evidence_ref,
            award.issuer_subject,
            award.issued_at,
            award.expires_at,
            revocation.created_at AS revoked_at,
            revocation.revoked_by,
            revocation.reason AS revocation_reason,
            (award.expires_at IS NOT NULL AND award.expires_at <= CURRENT_TIMESTAMP) AS expired,
            (revocation.id IS NOT NULL) AS revoked,
            (
                revocation.id IS NULL
                AND (award.expires_at IS NULL OR award.expires_at > CURRENT_TIMESTAMP)
            ) AS valid,
            'eay.academy.badge.v1'::varchar AS credential_profile,
            false AS signed_portable_credential
        FROM academy_badge_awards AS award
        JOIN academy_badge_definitions AS definition
          ON definition.tenant_id = award.tenant_id
         AND definition.id = award.badge_definition_id
        LEFT JOIN academy_badge_revocations AS revocation
          ON revocation.tenant_id = award.tenant_id
         AND revocation.badge_award_id = award.id
        """
    )

    for table_name in CREDENTIAL_TABLES:
        _tenant_policy(table_name)

    op.execute(f"GRANT SELECT ON {', '.join(CREDENTIAL_TABLES)} TO {RUNTIME_ROLE}")
    op.execute(
        f"GRANT SELECT ON academy_badge_definition_authority TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT ON academy_badge_credential_authority TO {RUNTIME_ROLE}"
    )
    op.execute(f"GRANT INSERT ON {', '.join(CREDENTIAL_TABLES)} TO {RUNTIME_ROLE}")
    op.execute(
        f"REVOKE UPDATE, DELETE ON {', '.join(CREDENTIAL_TABLES)} FROM {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS academy_badge_credential_authority")
    op.execute("DROP VIEW IF EXISTS academy_badge_definition_authority")
    for table_name in reversed(CREDENTIAL_TABLES):
        op.execute(f'DROP TRIGGER IF EXISTS "{table_name}_append_only" ON "{table_name}"')
    op.execute("DROP FUNCTION IF EXISTS academy_prevent_credential_mutation()")
    op.execute("DROP TRIGGER IF EXISTS academy_badge_award_evidence_guard ON academy_badge_awards")
    op.execute("DROP FUNCTION IF EXISTS academy_validate_badge_award()")
    for table_name in reversed(CREDENTIAL_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table_name}"')
