"""Add tenant-safe Academy product roles and broaden Academy content contracts.

Revision ID: 0018_academy_product_roles
Revises: 0017_merge_jarvis_platform_heads
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_academy_product_roles"
down_revision: str = "0017_merge_jarvis_platform_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACADEMY_LOCALES = ("tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR")
ACADEMY_CONTENT_TYPES = (
    "document",
    "video",
    "sop",
    "interactive",
    "live",
    "announcement",
    "poster",
    "survey",
)

ACADEMY_LEARNER = (
    "module:academy:view",
    "feature:academy:home",
    "feature:academy:catalog",
    "feature:academy:learningPaths",
    "feature:academy:player",
    "feature:academy:quizzes",
    "feature:academy:assignments",
    "feature:academy:certificates",
    "feature:academy:jarvisTutor",
)

ACADEMY_INSTRUCTOR = ACADEMY_LEARNER + (
    "feature:academy:contentStudio",
    "feature:academy:liveLearning",
    "action:academy:manageContent",
    "action:academy:managePaths",
    "action:academy:manageQuizzes",
    "action:academy:ingestDocuments",
    "action:academy:manageLiveLearning",
)

ACADEMY_ADMIN = ACADEMY_INSTRUCTOR + (
    "module:academy:admin",
    "feature:academy:audiences",
    "feature:academy:analytics",
    "action:academy:manageEntitlements",
    "action:academy:assignEnrollment",
    "action:academy:revokeCompletion",
    "action:academy:viewAnalytics",
)

NEW_PLATFORM_KEYS = (
    "module:insight:view",
    "module:jarvis:view",
    "feature:insight:overview",
    "feature:insight:canonicalMetrics",
    "feature:insight:trends",
    "feature:insight:drilldown",
    "feature:insight:provenance",
    "feature:insight:exports",
    "feature:jarvis:assistant",
    "feature:jarvis:operations",
    "feature:jarvis:academyTutor",
    "feature:jarvis:sources",
    "feature:jarvis:missions",
    "feature:jarvis:approvals",
    "feature:jarvis:history",
    "action:insight:view",
    "action:insight:drilldown",
    "action:insight:export",
    "action:jarvis:ask",
    "action:jarvis:proposeAction",
    "action:jarvis:approveAction",
    "action:jarvis:viewSources",
    "action:jarvis:viewHistory",
)

ROLE_POLICIES = {
    "academy_learner": ("Academy Learner", ACADEMY_LEARNER),
    "academy_instructor": ("Academy Instructor", ACADEMY_INSTRUCTOR),
    "academy_admin": ("Academy Admin", ACADEMY_ADMIN),
}


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    # Expand persisted Academy language/content contracts before the API starts
    # accepting them. UI, content versions and RAG chunks must share one truth.
    op.execute(
        "ALTER TABLE academy_content_versions "
        "DROP CONSTRAINT ck_academy_content_version_locale"
    )
    op.execute(
        f"""
        ALTER TABLE academy_content_versions
        ADD CONSTRAINT ck_academy_content_version_locale
        CHECK (locale = ANY({_sql_array(ACADEMY_LOCALES)}))
        """
    )
    op.execute("ALTER TABLE academy_document_chunks DROP CONSTRAINT ck_academy_chunk_locale")
    op.execute(
        f"""
        ALTER TABLE academy_document_chunks
        ADD CONSTRAINT ck_academy_chunk_locale
        CHECK (locale = ANY({_sql_array(ACADEMY_LOCALES)}))
        """
    )
    op.execute("ALTER TABLE academy_content_items DROP CONSTRAINT ck_academy_content_type")
    op.execute(
        f"""
        ALTER TABLE academy_content_items
        ADD CONSTRAINT ck_academy_content_type
        CHECK (content_type = ANY({_sql_array(ACADEMY_CONTENT_TYPES)}))
        """
    )

    # Refuse to turn a customer-defined role into a canonical system role.
    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM roles
                    WHERE key = '{escaped}' AND is_system IS FALSE
                ) THEN
                    RAISE EXCEPTION 'Canonical Academy role collision: {escaped}';
                END IF;
            END $$;
            """
        )

    # asyncpg-backed Alembic uses prepared statements, so keep every op.execute
    # to one SQL command while the surrounding Alembic transaction stays atomic.
    for role_key, (role_name, permissions) in ROLE_POLICIES.items():
        escaped_key = role_key.replace("'", "''")
        escaped_name = role_name.replace("'", "''")
        permission_array = _sql_array(tuple(permissions))

        op.execute(
            f"""
            INSERT INTO roles (tenant_id, key, name, is_system)
            SELECT id, '{escaped_key}', '{escaped_name}', TRUE
            FROM tenants
            ON CONFLICT (tenant_id, key)
            DO UPDATE SET name = EXCLUDED.name
            WHERE roles.is_system IS TRUE
            """
        )
        op.execute(
            f"""
            INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
            SELECT r.tenant_id, r.id, p.permission_key, '{{}}'::jsonb
            FROM roles AS r
            CROSS JOIN unnest({permission_array}) AS p(permission_key)
            WHERE r.key = '{escaped_key}' AND r.is_system IS TRUE
            ON CONFLICT (tenant_id, role_id, permission_key)
            DO UPDATE SET scope = '{{}}'::jsonb
            """
        )

    # Existing super-admin roles must immediately understand every new Academy,
    # Jarvis and Insight permission introduced by this release.
    super_admin_keys = tuple(sorted(set(ACADEMY_ADMIN + NEW_PLATFORM_KEYS)))
    op.execute(
        f"""
        INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
        SELECT r.tenant_id, r.id, p.permission_key, '{{}}'::jsonb
        FROM roles AS r
        CROSS JOIN unnest({_sql_array(super_admin_keys)}) AS p(permission_key)
        WHERE r.key = 'super_admin' AND r.is_system IS TRUE
        ON CONFLICT (tenant_id, role_id, permission_key)
        DO UPDATE SET scope = '{{}}'::jsonb
        """
    )


def downgrade() -> None:
    # Refuse a lossy downgrade if newer locale/type values are already in use.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM academy_content_versions
                WHERE locale NOT IN ('tr', 'en', 'de', 'ar')
            ) OR EXISTS (
                SELECT 1 FROM academy_document_chunks
                WHERE locale NOT IN ('tr', 'en', 'de', 'ar')
            ) OR EXISTS (
                SELECT 1 FROM academy_content_items
                WHERE content_type NOT IN ('document', 'video', 'sop')
            ) THEN
                RAISE EXCEPTION 'Academy downgrade would discard active locale/content contracts';
            END IF;
        END $$;
        """
    )

    created_keys = tuple(sorted(set(ACADEMY_ADMIN + NEW_PLATFORM_KEYS)))
    op.execute(
        f"""
        DELETE FROM role_permissions AS rp
        USING roles AS r
        WHERE rp.tenant_id = r.tenant_id
          AND rp.role_id = r.id
          AND r.key = 'super_admin'
          AND r.is_system IS TRUE
          AND rp.permission_key = ANY({_sql_array(created_keys)})
        """
    )

    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"""
            DELETE FROM role_permissions AS rp
            USING roles AS r
            WHERE rp.tenant_id = r.tenant_id
              AND rp.role_id = r.id
              AND r.key = '{escaped}'
              AND r.is_system IS TRUE
            """
        )
        op.execute(
            f"""
            DELETE FROM roles AS r
            WHERE r.key = '{escaped}'
              AND r.is_system IS TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM membership_roles AS mr
                  WHERE mr.tenant_id = r.tenant_id
                    AND mr.role_id = r.id
              )
            """
        )

    op.execute(
        "ALTER TABLE academy_content_versions "
        "DROP CONSTRAINT ck_academy_content_version_locale"
    )
    op.execute(
        """
        ALTER TABLE academy_content_versions
        ADD CONSTRAINT ck_academy_content_version_locale
        CHECK (locale IN ('tr', 'en', 'de', 'ar'))
        """
    )
    op.execute("ALTER TABLE academy_document_chunks DROP CONSTRAINT ck_academy_chunk_locale")
    op.execute(
        """
        ALTER TABLE academy_document_chunks
        ADD CONSTRAINT ck_academy_chunk_locale
        CHECK (locale IN ('tr', 'en', 'de', 'ar'))
        """
    )
    op.execute("ALTER TABLE academy_content_items DROP CONSTRAINT ck_academy_content_type")
    op.execute(
        """
        ALTER TABLE academy_content_items
        ADD CONSTRAINT ck_academy_content_type
        CHECK (content_type IN ('document', 'video', 'sop'))
        """
    )
