"""Repair canonical system-role integrity for every tenant.

Revision ID: 0006_system_role_integrity
Revises: 0005_system_role_permissions
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_system_role_integrity"
down_revision: str | None = "0005_system_role_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail closed: never silently convert a custom role into a
    # privileged canonical system role.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM roles
                WHERE key IN (
                    'super_admin',
                    'platform_admin',
                    'operator',
                    'viewer'
                )
                  AND is_system IS NOT TRUE
            ) THEN
                RAISE EXCEPTION
                    'Canonical role key exists as non-system role';
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        WITH desired_roles(role_key, role_name) AS (
            VALUES
            ('super_admin', 'Super Admin'),
            ('platform_admin', 'Platform Admin'),
            ('operator', 'Operator'),
            ('viewer', 'Viewer')
        )
        INSERT INTO roles (
            tenant_id,
            key,
            name,
            is_system
        )
        SELECT
            t.id,
            d.role_key,
            d.role_name,
            true
        FROM tenants AS t
        CROSS JOIN desired_roles AS d
        ON CONFLICT (tenant_id, key)
        DO UPDATE SET
            name = EXCLUDED.name,
            is_system = true
        """
    )

    op.execute(
        """
        WITH desired(role_key, permission_key) AS (
            VALUES
            ('platform_admin', 'module:admin_access:view'),
            ('super_admin', 'action:dockos:approve'),
            ('super_admin', 'action:dockos:create'),
            ('super_admin', 'action:dockos:delete'),
            ('super_admin', 'action:dockos:edit'),
            ('super_admin', 'action:dockos:export'),
            ('super_admin', 'action:dockos:view'),
            ('super_admin', 'action:planogram:approve'),
            ('super_admin', 'action:planogram:create'),
            ('super_admin', 'action:planogram:delete'),
            ('super_admin', 'action:planogram:edit'),
            ('super_admin', 'action:planogram:export'),
            ('super_admin', 'action:planogram:view'),
            ('super_admin', 'action:recruitment:approveRecruitmentRequest'),
            ('super_admin', 'action:workforce:approveAttendance'),
            ('super_admin', 'action:workforce:assignRosterTask'),
            ('super_admin', 'action:workforce:bulkApprove'),
            ('super_admin', 'action:workforce:bulkShiftUpload'),
            ('super_admin', 'action:workforce:createShift'),
            ('super_admin', 'action:workforce:export'),
            ('super_admin', 'action:workforce:importRoster'),
            ('super_admin', 'action:workforce:importTimeOff'),
            ('super_admin', 'action:workforce:manageAnnouncements'),
            ('super_admin', 'action:workforce:manageDevices'),
            ('super_admin', 'action:workforce:manageEmployees'),
            ('super_admin', 'action:workforce:manageHolidays'),
            ('super_admin', 'action:workforce:manageLeaves'),
            ('super_admin', 'action:workforce:manageNotifications'),
            ('super_admin', 'action:workforce:manageRules'),
            ('super_admin', 'action:workforce:manageStaffingNorms'),
            ('super_admin', 'action:workforce:manageSystemConfig'),
            ('super_admin', 'action:workforce:manageWarehouses'),
            ('super_admin', 'action:workforce:manualCorrection'),
            ('super_admin', 'action:workforce:overrideRoster'),
            ('super_admin', 'action:workforce:printAttendance'),
            ('super_admin', 'action:workforce:resolveManagerTasks'),
            ('super_admin', 'action:workforce:runPayrollClose'),
            ('super_admin', 'action:workforce:viewAuditLog'),
            ('super_admin', 'action:workforce:viewFullNationalId'),
            ('super_admin', 'feature:dockos:dashboard'),
            ('super_admin', 'feature:dockos:duplicateResolution'),
            ('super_admin', 'feature:dockos:excelUpload'),
            ('super_admin', 'feature:dockos:livePurchaseOrders'),
            ('super_admin', 'feature:dockos:shipmentDetails'),
            ('super_admin', 'feature:dockos:supplierAppointments'),
            ('super_admin', 'feature:dockos:vehicleTracking'),
            ('super_admin', 'feature:planogram:aiRecommend'),
            ('super_admin', 'feature:planogram:fixtureEdit'),
            ('super_admin', 'feature:planogram:layoutEdit'),
            ('super_admin', 'feature:planogram:layoutView'),
            ('super_admin', 'feature:planogram:productAssign'),
            ('super_admin', 'feature:planogram:ruleEdit'),
            ('super_admin', 'feature:workforce:approvals'),
            ('super_admin', 'feature:workforce:attendance'),
            ('super_admin', 'feature:workforce:audit'),
            ('super_admin', 'feature:workforce:communications'),
            ('super_admin', 'feature:workforce:dashboard'),
            ('super_admin', 'feature:workforce:devices'),
            ('super_admin', 'feature:workforce:leaves'),
            ('super_admin', 'feature:workforce:managerTasks'),
            ('super_admin', 'feature:workforce:opexLab'),
            ('super_admin', 'feature:workforce:periodClose'),
            ('super_admin', 'feature:workforce:pickerApp'),
            ('super_admin', 'feature:workforce:rules'),
            ('super_admin', 'feature:workforce:shifts'),
            ('super_admin', 'feature:workforce:systemConfig'),
            ('super_admin', 'feature:workforce:timesheet'),
            ('super_admin', 'feature:workforce:warehouses'),
            ('super_admin', 'module:admin_access:admin'),
            ('super_admin', 'module:admin_access:view'),
            ('super_admin', 'module:budget:view'),
            ('super_admin', 'module:dockos:view'),
            ('super_admin', 'module:inventory:view'),
            ('super_admin', 'module:planogram:admin'),
            ('super_admin', 'module:planogram:view'),
            ('super_admin', 'module:recruitment:view'),
            ('super_admin', 'module:workforce:view')
        )
        INSERT INTO role_permissions (
            tenant_id,
            role_id,
            permission_key,
            scope
        )
        SELECT
            r.tenant_id,
            r.id,
            d.permission_key,
            '{}'::jsonb
        FROM roles AS r
        JOIN desired AS d
          ON d.role_key = r.key
        WHERE r.is_system = true
        ON CONFLICT (
            tenant_id,
            role_id,
            permission_key
        )
        DO NOTHING
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "0006_system_role_integrity is an irreversible "
        "security-integrity migration"
    )
