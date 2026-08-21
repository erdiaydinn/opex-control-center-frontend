"""Provision canonical product system roles for tenants created after migrations.

Revision ID: 0048_product_role_provisioning
Revises: 0047_academy_scenario_content_binding
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048_product_role_provisioning"
down_revision: str | None = "0047_academy_scenario_content_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
FIELD_WORKER = (
    "module:field_intelligence:view",
    "feature:field_intelligence:missions",
    "feature:field_intelligence:capture",
    "action:field_intelligence:submitEvidence",
)
FIELD_MANAGER = FIELD_WORKER + (
    "module:field_intelligence:admin",
    "feature:field_intelligence:commandCenter",
    "feature:field_intelligence:missionBuilder",
    "feature:field_intelligence:evidenceReview",
    "feature:field_intelligence:targeting",
    "feature:field_intelligence:templates",
    "feature:field_intelligence:analytics",
    "feature:field_intelligence:promotions",
    "feature:field_intelligence:governance",
    "action:field_intelligence:createMission",
    "action:field_intelligence:activateMission",
    "action:field_intelligence:cancelMission",
    "action:field_intelligence:sendReminder",
    "action:field_intelligence:reviewEvidence",
    "action:field_intelligence:manageTemplates",
    "action:field_intelligence:manageLocations",
    "action:field_intelligence:exportResults",
    "action:field_intelligence:viewEvidence",
    "action:field_intelligence:proposePromotion",
    "action:field_intelligence:approvePromotion",
    "action:field_intelligence:viewPromotions",
    "action:field_intelligence:manageRecurrence",
    "action:field_intelligence:exemptTarget",
    "action:field_intelligence:approveExport",
)
PLANOGRAM_EDITOR = (
    "module:planogram:view",
    "feature:planogram:layoutView",
    "feature:planogram:layoutEdit",
    "feature:planogram:fixtureEdit",
    "action:planogram:view",
    "action:planogram:create",
    "action:planogram:edit",
    "action:planogram:export",
)
PLANOGRAM_ADMIN = PLANOGRAM_EDITOR + (
    "module:planogram:admin",
    "feature:planogram:ruleEdit",
    "feature:planogram:productAssign",
    "feature:planogram:aiRecommend",
    "action:planogram:approve",
    "action:planogram:delete",
    "action:planogram:acceptFieldEvidence",
)

ROLE_POLICIES = {
    "academy_learner": ("Academy Learner", ACADEMY_LEARNER),
    "academy_instructor": ("Academy Instructor", ACADEMY_INSTRUCTOR),
    "academy_admin": ("Academy Admin", ACADEMY_ADMIN),
    "field_worker": ("Field Worker", FIELD_WORKER),
    "field_manager": ("Field Manager", FIELD_MANAGER),
    "planogram_editor": ("Planogram Editor", PLANOGRAM_EDITOR),
    "planogram_admin": ("Planogram Admin", PLANOGRAM_ADMIN),
}


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    role_keys = ", ".join("'" + key.replace("'", "''") + "'" for key in ROLE_POLICIES)
    op.execute(
        f"""
        DO $guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM roles
                WHERE key IN ({role_keys})
                  AND is_system IS FALSE
            ) THEN
                RAISE EXCEPTION
                    'Canonical product role key exists as non-system role';
            END IF;
        END
        $guard$
        """
    )

    # Backfill idempotently so older tenants and test fixtures converge to the
    # same product-role contract before the new-tenant trigger is enabled.
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
            DO UPDATE SET name=EXCLUDED.name
            WHERE roles.is_system IS TRUE
            """
        )
        op.execute(
            f"""
            INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
            SELECT r.tenant_id, r.id, p.permission_key, '{{}}'::jsonb
            FROM roles AS r
            CROSS JOIN unnest({permission_array}) AS p(permission_key)
            WHERE r.key='{escaped_key}' AND r.is_system IS TRUE
            ON CONFLICT (tenant_id, role_id, permission_key)
            DO UPDATE SET scope='{{}}'::jsonb
            """
        )

    role_values = ",\n                ".join(
        f"('{key.replace(chr(39), chr(39) * 2)}', '{name.replace(chr(39), chr(39) * 2)}', {_sql_array(tuple(perms))})"
        for key, (name, perms) in ROLE_POLICIES.items()
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION eay_provision_product_roles_for_new_tenant()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        DECLARE
            role_record record;
            provisioned_role_id uuid;
            provisioned_permission_key varchar;
        BEGIN
            FOR role_record IN
                SELECT *
                FROM (VALUES
                    {role_values}
                ) AS desired(role_key, role_name, permissions)
            LOOP
                INSERT INTO roles (tenant_id, key, name, is_system)
                VALUES (NEW.id, role_record.role_key, role_record.role_name, TRUE)
                ON CONFLICT (tenant_id, key)
                DO UPDATE SET name=EXCLUDED.name
                WHERE roles.is_system IS TRUE
                RETURNING id INTO provisioned_role_id;

                IF provisioned_role_id IS NULL THEN
                    RAISE EXCEPTION
                        'Canonical product role collision for tenant % role %',
                        NEW.id,
                        role_record.role_key;
                END IF;

                FOREACH provisioned_permission_key IN ARRAY role_record.permissions
                LOOP
                    INSERT INTO role_permissions (
                        tenant_id, role_id, permission_key, scope
                    ) VALUES (
                        NEW.id,
                        provisioned_role_id,
                        provisioned_permission_key,
                        '{{}}'::jsonb
                    )
                    ON CONFLICT (tenant_id, role_id, permission_key)
                    DO UPDATE SET scope='{{}}'::jsonb;
                END LOOP;
            END LOOP;
            RETURN NEW;
        END;
        $body$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tenants_provision_product_roles
        AFTER INSERT ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION eay_provision_product_roles_for_new_tenant()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tenants_provision_product_roles ON tenants")
    op.execute("DROP FUNCTION IF EXISTS eay_provision_product_roles_for_new_tenant()")
