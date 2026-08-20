"""Provision canonical Recruitment HR product authority.

Revision ID: 0051_workforce_hiring_product_role
Revises: 0050_academy_credential_authority

The role is intentionally separate from tenant-defined HR roles. Existing custom
roles are never silently escalated. The product role can be assigned explicitly
through the canonical membership-role authority.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0051_workforce_hiring_product_role"
down_revision: str | None = "0050_academy_credential_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_KEY = "recruitment_hr"
ROLE_NAME = "Recruitment HR"
PERMISSIONS = (
    "module:recruitment:view",
    "action:recruitment:viewRecruitment",
    "action:recruitment:createRecruitmentRequest",
    "action:recruitment:approveRecruitmentRequest",
    "action:recruitment:viewRecruitmentEvidence",
    "action:recruitment:manageRecruitmentNorms",
    "action:recruitment:manageRecruitmentActuals",
    "action:recruitment:manageRecruitmentSettings",
    "action:recruitment:manageRecruitmentNotifications",
)
SUPER_ADMIN_ADDITIONS = (
    "action:recruitment:manageRecruitmentActuals",
    "action:recruitment:viewRecruitmentEvidence",
    "action:recruitment:manageRecruitmentNorms",
    "action:recruitment:manageRecruitmentSettings",
    "action:recruitment:manageRecruitmentNotifications",
    "action:recruitment:createRecruitmentRequest",
    "action:recruitment:viewRecruitment",
)


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    permission_array = _sql_array(PERMISSIONS)
    super_admin_array = _sql_array(SUPER_ADMIN_ADDITIONS)

    op.execute(
        f"""
        DO $guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM roles
                WHERE key = '{ROLE_KEY}'
                  AND is_system IS FALSE
            ) THEN
                RAISE EXCEPTION
                    'Canonical Recruitment HR role key exists as a non-system role';
            END IF;
        END
        $guard$
        """
    )

    op.execute(
        f"""
        INSERT INTO roles (tenant_id, key, name, is_system)
        SELECT id, '{ROLE_KEY}', '{ROLE_NAME}', TRUE
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
        WHERE r.key = '{ROLE_KEY}'
          AND r.is_system IS TRUE
        ON CONFLICT (tenant_id, role_id, permission_key)
        DO UPDATE SET scope='{{}}'::jsonb
        """
    )

    # Super Admin already owns canonical platform authority. Keep the new
    # capability visible to that role without granting it to arbitrary HR roles.
    op.execute(
        f"""
        INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
        SELECT r.tenant_id, r.id, p.permission_key, '{{}}'::jsonb
        FROM roles AS r
        CROSS JOIN unnest({super_admin_array}) AS p(permission_key)
        WHERE r.key = 'super_admin'
          AND r.is_system IS TRUE
        ON CONFLICT (tenant_id, role_id, permission_key)
        DO UPDATE SET scope='{{}}'::jsonb
        """
    )

    # 0048 owns the broader product-role trigger. Keep this migration additive
    # and isolated so Academy/Field/Planogram role contracts are not rewritten.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION eay_provision_recruitment_hr_for_new_tenant()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $body$
        DECLARE
            provisioned_role_id uuid;
            provisioned_permission_key varchar;
        BEGIN
            INSERT INTO roles (tenant_id, key, name, is_system)
            VALUES (NEW.id, '{ROLE_KEY}', '{ROLE_NAME}', TRUE)
            ON CONFLICT (tenant_id, key)
            DO UPDATE SET name=EXCLUDED.name
            WHERE roles.is_system IS TRUE
            RETURNING id INTO provisioned_role_id;

            IF provisioned_role_id IS NULL THEN
                RAISE EXCEPTION
                    'Canonical Recruitment HR role collision for tenant %',
                    NEW.id;
            END IF;

            FOREACH provisioned_permission_key IN ARRAY {permission_array}
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
            RETURN NEW;
        END;
        $body$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tenants_provision_recruitment_hr
        AFTER INSERT ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION eay_provision_recruitment_hr_for_new_tenant()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tenants_provision_recruitment_hr ON tenants")
    op.execute("DROP FUNCTION IF EXISTS eay_provision_recruitment_hr_for_new_tenant()")
    op.execute(
        f"""
        DELETE FROM role_permissions AS rp
        USING roles AS r
        WHERE rp.tenant_id = r.tenant_id
          AND rp.role_id = r.id
          AND r.key = 'super_admin'
          AND r.is_system IS TRUE
          AND rp.permission_key = ANY({_sql_array(SUPER_ADMIN_ADDITIONS)})
        """
    )
    op.execute(
        f"""
        DELETE FROM roles
        WHERE key = '{ROLE_KEY}'
          AND is_system IS TRUE
        """
    )
