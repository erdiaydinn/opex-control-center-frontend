import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.permission_catalog import SYSTEM_ROLE_PERMISSIONS

SYSTEM_ROLE_NAMES = {
    "super_admin": "Super Admin",
    "platform_admin": "Platform Admin",
    "operator": "Operator",
    "viewer": "Viewer",
    "academy_learner": "Academy Learner",
    "academy_instructor": "Academy Instructor",
    "academy_admin": "Academy Admin",
}

if set(SYSTEM_ROLE_NAMES) != set(SYSTEM_ROLE_PERMISSIONS):
    raise RuntimeError(
        "System role names and permission policy are out of sync"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap tenant system roles and the first super admin."
    )
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--admin-subject", required=True)
    return parser.parse_args()


async def bootstrap(args: argparse.Namespace) -> None:
    settings = get_settings()

    engine = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
    )

    tenant_id = str(args.tenant_id)

    permission_payload = json.dumps(
        [
            {
                "role_key": role_key,
                "permission_key": permission_key,
            }
            for role_key in sorted(SYSTEM_ROLE_PERMISSIONS)
            for permission_key in sorted(
                SYSTEM_ROLE_PERMISSIONS[role_key]
            )
        ],
        separators=(",", ":"),
    )

    role_keys = sorted(SYSTEM_ROLE_PERMISSIONS)

    try:
        async with engine.begin() as connection:
            tenant = (
                await connection.execute(
                    text(
                        """
                        SELECT slug, status
                        FROM tenants
                        WHERE id = CAST(:tenant_id AS UUID)
                        """
                    ),
                    {"tenant_id": tenant_id},
                )
            ).mappings().first()

            if tenant is None:
                await connection.execute(
                    text(
                        """
                        INSERT INTO tenants (
                            id,
                            slug,
                            display_name,
                            status
                        )
                        VALUES (
                            CAST(:tenant_id AS UUID),
                            :slug,
                            :display_name,
                            'active'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "slug": args.tenant_slug,
                        "display_name": args.tenant_name,
                    },
                )
            else:
                if tenant["slug"] != args.tenant_slug:
                    raise RuntimeError(
                        "Tenant ID already exists with a different slug"
                    )

                if tenant["status"] != "active":
                    raise RuntimeError(
                        "Bootstrap refuses to reactivate a non-active tenant"
                    )

            for role_key in role_keys:
                role_name = SYSTEM_ROLE_NAMES[role_key]

                role_result = await connection.execute(
                    text(
                        """
                        INSERT INTO roles (
                            tenant_id,
                            key,
                            name,
                            is_system
                        )
                        VALUES (
                            CAST(:tenant_id AS UUID),
                            :role_key,
                            :role_name,
                            true
                        )
                        ON CONFLICT (tenant_id, key)
                        DO UPDATE SET
                            name = EXCLUDED.name
                        WHERE roles.is_system IS TRUE
                        RETURNING is_system
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "role_key": role_key,
                        "role_name": role_name,
                    },
                )

                if role_result.scalar_one_or_none() is not True:
                    raise RuntimeError(
                        "Bootstrap refuses canonical role collision: "
                        f"{role_key}"
                    )

            # Canonical system-role permissions are authoritative.
            # Unexpected permissions are removed, missing permissions inserted,
            # and canonical scopes normalized to {}. The target role list is
            # parameterized so product roles can evolve without shadow SQL lists.
            await connection.execute(
                text(
                    """
                    WITH desired AS (
                        SELECT
                            item.role_key,
                            item.permission_key
                        FROM jsonb_to_recordset(
                            CAST(:permission_payload AS jsonb)
                        ) AS item(
                            role_key text,
                            permission_key text
                        )
                    ),
                    target_roles AS (
                        SELECT
                            r.tenant_id,
                            r.id AS role_id,
                            r.key AS role_key
                        FROM roles AS r
                        WHERE r.tenant_id = CAST(:tenant_id AS UUID)
                          AND r.is_system IS TRUE
                          AND r.key = ANY(CAST(:role_keys AS varchar[]))
                    ),
                    deleted AS (
                        DELETE FROM role_permissions AS rp
                        USING target_roles AS tr
                        WHERE rp.tenant_id = tr.tenant_id
                          AND rp.role_id = tr.role_id
                          AND NOT EXISTS (
                              SELECT 1
                              FROM desired AS d
                              WHERE d.role_key = tr.role_key
                                AND d.permission_key = rp.permission_key
                          )
                        RETURNING rp.id
                    )
                    INSERT INTO role_permissions (
                        tenant_id,
                        role_id,
                        permission_key,
                        scope
                    )
                    SELECT
                        tr.tenant_id,
                        tr.role_id,
                        d.permission_key,
                        '{}'::jsonb
                    FROM target_roles AS tr
                    JOIN desired AS d
                      ON d.role_key = tr.role_key
                    ON CONFLICT (
                        tenant_id,
                        role_id,
                        permission_key
                    )
                    DO UPDATE SET
                        scope = '{}'::jsonb
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "permission_payload": permission_payload,
                    "role_keys": role_keys,
                },
            )

            membership = (
                await connection.execute(
                    text(
                        """
                        SELECT id, status
                        FROM memberships
                        WHERE tenant_id = CAST(:tenant_id AS UUID)
                          AND external_subject = :subject
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "subject": args.admin_subject,
                    },
                )
            ).mappings().first()

            if membership is None:
                membership_id = await connection.scalar(
                    text(
                        """
                        INSERT INTO memberships (
                            tenant_id,
                            external_subject,
                            status
                        )
                        VALUES (
                            CAST(:tenant_id AS UUID),
                            :subject,
                            'active'
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "subject": args.admin_subject,
                    },
                )
            else:
                if membership["status"] != "active":
                    raise RuntimeError(
                        "Bootstrap refuses to reactivate a non-active membership"
                    )

                membership_id = membership["id"]

            await connection.execute(
                text(
                    """
                    INSERT INTO membership_roles (
                        tenant_id,
                        membership_id,
                        role_id
                    )
                    SELECT
                        CAST(:tenant_id AS UUID),
                        CAST(:membership_id AS UUID),
                        r.id
                    FROM roles AS r
                    WHERE r.tenant_id = CAST(:tenant_id AS UUID)
                      AND r.key = 'super_admin'
                      AND r.is_system IS TRUE
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "membership_id": str(membership_id),
                },
            )

        print(
            "Bootstrap complete: "
            f"tenant={args.tenant_slug} "
            f"admin_subject={args.admin_subject}"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap(parse_args()))
