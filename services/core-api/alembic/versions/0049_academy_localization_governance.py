"""Add tenant-scoped Academy localization governance and translation lineage.

Revision ID: 0049_academy_localization_governance
Revises: 0048_product_role_provisioning
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049_academy_localization_governance"
down_revision: str | None = "0048_product_role_provisioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
LOCALIZATION_TABLES = (
    "academy_locale_settings",
    "academy_translation_lineage",
    "academy_translation_review_events",
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
    # This reference key lets both source and target FKs prove that the two
    # versions belong to the same tenant, content item and exact locale.
    op.execute(
        """
        ALTER TABLE academy_content_versions
        ADD CONSTRAINT uq_academy_content_version_lineage_ref
        UNIQUE (tenant_id, content_id, id, locale)
        """
    )

    op.execute(
        """
        CREATE TABLE academy_locale_settings (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            locale varchar(16) NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            required boolean NOT NULL DEFAULT false,
            is_default boolean NOT NULL DEFAULT false,
            allow_machine_draft boolean NOT NULL DEFAULT false,
            created_by varchar(255) NOT NULL,
            updated_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, locale),
            CONSTRAINT ck_academy_locale_setting_shape
                CHECK (locale = btrim(locale) AND char_length(locale) BETWEEN 2 AND 16),
            CONSTRAINT ck_academy_locale_required_enabled
                CHECK (NOT required OR enabled),
            CONSTRAINT ck_academy_locale_default_enabled
                CHECK (NOT is_default OR enabled)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_academy_locale_settings_one_default
        ON academy_locale_settings (tenant_id)
        WHERE is_default
        """
    )

    # Keep the platform's canonical English fallback available for every tenant,
    # while also preserving every locale already present in Academy content.
    op.execute(
        """
        INSERT INTO academy_locale_settings (
            tenant_id, locale, enabled, required, is_default,
            allow_machine_draft, created_by, updated_by
        )
        SELECT id, 'en', true, false, true, false, 'migration-0049', 'migration-0049'
        FROM tenants
        ON CONFLICT (tenant_id, locale) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO academy_locale_settings (
            tenant_id, locale, enabled, required, is_default,
            allow_machine_draft, created_by, updated_by
        )
        SELECT DISTINCT
            tenant_id, locale, true, false, false, false,
            'migration-0049', 'migration-0049'
        FROM academy_content_versions
        ON CONFLICT (tenant_id, locale) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE FUNCTION academy_provision_locale_policy_for_new_tenant()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        DECLARE
            actor varchar(255);
        BEGIN
            actor := COALESCE(
                NULLIF(current_setting('app.actor_subject', true), ''),
                'tenant-provisioning'
            );
            INSERT INTO academy_locale_settings (
                tenant_id, locale, enabled, required, is_default,
                allow_machine_draft, created_by, updated_by
            ) VALUES (
                NEW.id, 'en', true, false, true, false, actor, actor
            )
            ON CONFLICT (tenant_id, locale) DO NOTHING;
            RETURN NEW;
        END;
        $body$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tenants_provision_academy_locale_policy
        AFTER INSERT ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION academy_provision_locale_policy_for_new_tenant()
        """
    )

    op.execute(
        """
        CREATE TABLE academy_translation_lineage (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            content_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            source_locale varchar(16) NOT NULL,
            target_version_id uuid NOT NULL,
            target_locale varchar(16) NOT NULL,
            translation_method varchar(30) NOT NULL,
            translator_subject varchar(255) NOT NULL,
            source_sha256_snapshot char(64),
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_translation_content
                FOREIGN KEY (tenant_id, content_id)
                REFERENCES academy_content_items(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT fk_academy_translation_source
                FOREIGN KEY (tenant_id, content_id, source_version_id, source_locale)
                REFERENCES academy_content_versions(tenant_id, content_id, id, locale)
                ON DELETE RESTRICT,
            CONSTRAINT fk_academy_translation_target
                FOREIGN KEY (tenant_id, content_id, target_version_id, target_locale)
                REFERENCES academy_content_versions(tenant_id, content_id, id, locale)
                ON DELETE RESTRICT,
            CONSTRAINT ck_academy_translation_distinct_versions
                CHECK (source_version_id <> target_version_id),
            CONSTRAINT ck_academy_translation_distinct_locales
                CHECK (source_locale <> target_locale),
            CONSTRAINT ck_academy_translation_method
                CHECK (translation_method IN ('human', 'machine_assisted', 'machine_draft')),
            CONSTRAINT ck_academy_translation_source_sha
                CHECK (
                    source_sha256_snapshot IS NULL
                    OR source_sha256_snapshot ~ '^[0-9a-f]{64}$'
                ),
            CONSTRAINT uq_academy_translation_target_version
                UNIQUE (tenant_id, target_version_id),
            CONSTRAINT uq_academy_translation_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE academy_translation_review_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            translation_id uuid NOT NULL,
            event_type varchar(20) NOT NULL,
            actor_subject varchar(255) NOT NULL,
            reason text,
            request_id varchar(128) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_academy_translation_review_lineage
                FOREIGN KEY (tenant_id, translation_id)
                REFERENCES academy_translation_lineage(tenant_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_academy_translation_review_type
                CHECK (event_type IN ('submitted', 'approved', 'rejected')),
            CONSTRAINT ck_academy_translation_rejection_reason
                CHECK (
                    event_type <> 'rejected'
                    OR NULLIF(btrim(reason), '') IS NOT NULL
                ),
            CONSTRAINT uq_academy_translation_review_request
                UNIQUE (tenant_id, translation_id, request_id, event_type),
            CONSTRAINT uq_academy_translation_review_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION academy_validate_translation_review_event()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        DECLARE
            translator varchar(255);
            latest_event varchar(20);
        BEGIN
            -- Serialize review-state transitions without granting UPDATE on the
            -- immutable lineage table. SELECT ... FOR UPDATE would require the
            -- runtime role to hold UPDATE privilege and would weaken that boundary.
            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.translation_id::text, 0)
            );

            SELECT translator_subject
            INTO translator
            FROM academy_translation_lineage
            WHERE tenant_id = NEW.tenant_id
              AND id = NEW.translation_id;

            IF translator IS NULL THEN
                RAISE EXCEPTION 'Academy translation lineage not found';
            END IF;

            SELECT event_type
            INTO latest_event
            FROM academy_translation_review_events
            WHERE tenant_id = NEW.tenant_id
              AND translation_id = NEW.translation_id
            ORDER BY created_at DESC, id DESC
            LIMIT 1;

            IF NEW.event_type = 'submitted' THEN
                IF latest_event IS NOT NULL AND latest_event <> 'rejected' THEN
                    RAISE EXCEPTION 'Translation is not eligible for submission';
                END IF;
            ELSE
                IF latest_event IS DISTINCT FROM 'submitted' THEN
                    RAISE EXCEPTION 'Translation must be submitted before review';
                END IF;
                IF NEW.actor_subject = translator THEN
                    RAISE EXCEPTION 'Translator cannot review own translation';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $body$
        """
    )
    op.execute(
        """
        CREATE TRIGGER academy_translation_review_state_guard
        BEFORE INSERT ON academy_translation_review_events
        FOR EACH ROW
        EXECUTE FUNCTION academy_validate_translation_review_event()
        """
    )

    op.execute(
        """
        CREATE VIEW academy_translation_authority
        WITH (security_invoker = true) AS
        WITH latest_review AS (
            SELECT DISTINCT ON (tenant_id, translation_id)
                tenant_id,
                translation_id,
                event_type,
                actor_subject AS reviewer_subject,
                reason AS review_reason,
                created_at AS reviewed_at
            FROM academy_translation_review_events
            ORDER BY tenant_id, translation_id, created_at DESC, id DESC
        ),
        latest_source AS (
            SELECT DISTINCT ON (tenant_id, content_id, locale)
                tenant_id,
                content_id,
                locale,
                id AS version_id
            FROM academy_content_versions
            WHERE status = 'published'
            ORDER BY
                tenant_id,
                content_id,
                locale,
                version_number DESC,
                published_at DESC NULLS LAST,
                created_at DESC,
                id DESC
        )
        SELECT
            lineage.tenant_id,
            lineage.id AS translation_id,
            lineage.content_id,
            lineage.source_version_id,
            lineage.source_locale,
            lineage.target_version_id,
            lineage.target_locale,
            lineage.translation_method,
            lineage.translator_subject,
            CASE
                WHEN review.event_type = 'submitted' THEN 'in_review'
                WHEN review.event_type = 'approved' THEN 'approved'
                WHEN review.event_type = 'rejected' THEN 'rejected'
                ELSE 'draft'
            END AS workflow_status,
            review.reviewer_subject,
            review.review_reason,
            review.reviewed_at,
            latest.version_id AS latest_published_source_version_id,
            (
                source.status <> 'published'
                OR target.status <> 'published'
                OR latest.version_id IS NULL
                OR latest.version_id <> lineage.source_version_id
            ) AS stale,
            (
                review.event_type = 'approved'
                AND source.status = 'published'
                AND target.status = 'published'
                AND latest.version_id = lineage.source_version_id
                AND COALESCE(locale_setting.enabled, false)
            ) AS authoritative
        FROM academy_translation_lineage AS lineage
        JOIN academy_content_versions AS source
          ON source.tenant_id = lineage.tenant_id
         AND source.id = lineage.source_version_id
         AND source.content_id = lineage.content_id
         AND source.locale = lineage.source_locale
        JOIN academy_content_versions AS target
          ON target.tenant_id = lineage.tenant_id
         AND target.id = lineage.target_version_id
         AND target.content_id = lineage.content_id
         AND target.locale = lineage.target_locale
        LEFT JOIN latest_review AS review
          ON review.tenant_id = lineage.tenant_id
         AND review.translation_id = lineage.id
        LEFT JOIN latest_source AS latest
          ON latest.tenant_id = lineage.tenant_id
         AND latest.content_id = lineage.content_id
         AND latest.locale = lineage.source_locale
        LEFT JOIN academy_locale_settings AS locale_setting
          ON locale_setting.tenant_id = lineage.tenant_id
         AND locale_setting.locale = lineage.target_locale
        """
    )

    for table_name in LOCALIZATION_TABLES:
        _tenant_policy(table_name)

    op.execute(
        f"GRANT SELECT ON {', '.join(LOCALIZATION_TABLES)} TO {RUNTIME_ROLE}"
    )
    op.execute(f"GRANT SELECT ON academy_translation_authority TO {RUNTIME_ROLE}")
    op.execute(
        f"GRANT INSERT, UPDATE ON academy_locale_settings TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"REVOKE DELETE ON academy_locale_settings FROM {RUNTIME_ROLE}"
    )
    op.execute(
        "GRANT INSERT ON academy_translation_lineage, "
        f"academy_translation_review_events TO {RUNTIME_ROLE}"
    )
    op.execute(
        "REVOKE UPDATE, DELETE ON academy_translation_lineage, "
        f"academy_translation_review_events FROM {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS academy_translation_authority")
    op.execute(
        "DROP TRIGGER IF EXISTS academy_translation_review_state_guard "
        "ON academy_translation_review_events"
    )
    op.execute("DROP FUNCTION IF EXISTS academy_validate_translation_review_event()")
    for table_name in reversed(LOCALIZATION_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    op.execute("DROP TRIGGER IF EXISTS tenants_provision_academy_locale_policy ON tenants")
    op.execute("DROP FUNCTION IF EXISTS academy_provision_locale_policy_for_new_tenant()")
    op.execute(
        """
        ALTER TABLE academy_content_versions
        DROP CONSTRAINT IF EXISTS uq_academy_content_version_lineage_ref
        """
    )
