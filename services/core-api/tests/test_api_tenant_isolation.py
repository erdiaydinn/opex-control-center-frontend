from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.main import app

TENANT_A = UUID("00000000-0000-0000-0000-0000000000b1")
TENANT_B = UUID("00000000-0000-0000-0000-0000000000b2")


async def set_tenant_context(connection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def delete_tenant(connection, tenant_id: UUID) -> None:
    await set_tenant_context(connection, tenant_id)
    await connection.execute(
        text("DELETE FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": tenant_id},
    )


async def seed_tenant_user(
    connection,
    *,
    tenant_id: UUID,
    slug: str,
    subject: str,
    role_key: str,
):
    await set_tenant_context(connection, tenant_id)

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
                :tenant_id,
                :slug,
                :display_name,
                'active'
            )
            ON CONFLICT (id)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                status = 'active'
            """
        ),
        {
            "tenant_id": tenant_id,
            "slug": slug,
            "display_name": slug,
        },
    )

    for key, name in (
        ("super_admin", "Super Admin"),
        ("viewer", "Viewer"),
    ):
        await connection.execute(
            text(
                """
                INSERT INTO roles (
                    tenant_id,
                    key,
                    name,
                    is_system
                )
                VALUES (
                    :tenant_id,
                    :key,
                    :name,
                    true
                )
                ON CONFLICT (tenant_id, key)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    is_system = true
                """
            ),
            {
                "tenant_id": tenant_id,
                "key": key,
                "name": name,
            },
        )

    membership_id = await connection.scalar(
        text(
            """
            INSERT INTO memberships (
                tenant_id,
                external_subject,
                status
            )
            VALUES (
                :tenant_id,
                :subject,
                'active'
            )
            ON CONFLICT (tenant_id, external_subject)
            DO UPDATE SET status = 'active'
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "subject": subject,
        },
    )

    await connection.execute(
        text(
            """
            DELETE FROM membership_roles
            WHERE tenant_id = :tenant_id
              AND membership_id = :membership_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "membership_id": membership_id,
        },
    )

    await connection.execute(
        text(
            """
            INSERT INTO membership_roles (
                tenant_id,
                membership_id,
                role_id
            )
            SELECT
                :tenant_id,
                :membership_id,
                id
            FROM roles
            WHERE tenant_id = :tenant_id
              AND key = :role_key
            """
        ),
        {
            "tenant_id": tenant_id,
            "membership_id": membership_id,
            "role_key": role_key,
        },
    )

    return membership_id


@pytest.mark.asyncio
async def test_api_blocks_cross_tenant_member_access() -> None:
    engine = create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as connection:
            await seed_tenant_user(
                connection,
                tenant_id=TENANT_A,
                slug="api-isolation-a",
                subject="tenant-a-admin",
                role_key="super_admin",
            )

        async with engine.begin() as connection:
            tenant_b_member_id = await seed_tenant_user(
                connection,
                tenant_id=TENANT_B,
                slug="api-isolation-b",
                subject="tenant-b-user",
                role_key="viewer",
            )

        tenant_a_token = (
            f"dev.tenant-a-admin.{TENANT_A}.super_admin"
        )
        tenant_b_token = (
            f"dev.tenant-b-user.{TENANT_B}.viewer"
        )

        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            members_response = await client.get(
                "/v1/admin/members",
                headers={
                    "Authorization": f"Bearer {tenant_a_token}"
                },
            )

            assert members_response.status_code == 200
            assert "tenant-a-admin" in members_response.text
            assert "tenant-b-user" not in members_response.text

            cross_tenant_patch = await client.patch(
                f"/v1/admin/members/{tenant_b_member_id}",
                headers={
                    "Authorization": f"Bearer {tenant_a_token}"
                },
                json={
                    "status": "suspended",
                    "roles": ["viewer"],
                },
            )

            assert cross_tenant_patch.status_code == 404

            tenant_b_context = await client.get(
                "/v1/context",
                headers={
                    "Authorization": f"Bearer {tenant_b_token}"
                },
            )

            assert tenant_b_context.status_code == 200

        # Verify the rejected attack did not mutate Tenant B.
        async with engine.begin() as connection:
            await set_tenant_context(connection, TENANT_B)

            status_value = await connection.scalar(
                text(
                    """
                    SELECT status
                    FROM memberships
                    WHERE id = :membership_id
                    """
                ),
                {"membership_id": tenant_b_member_id},
            )

            assert status_value == "active"

    finally:
        await engine.dispose()




@pytest.mark.asyncio
async def test_denied_authenticated_request_keeps_actor_in_audit() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-0000000000b3")
    subject = "audit-denied-attacker"

    engine = create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as connection:
            membership_id = await seed_tenant_user(
                connection,
                tenant_id=tenant_id,
                slug="audit-denied-identity",
                subject=subject,
                role_key="viewer",
            )

            await set_tenant_context(connection, tenant_id)
            await connection.execute(
                text(
                    """
                    UPDATE memberships
                    SET status = 'suspended'
                    WHERE id = :membership_id
                    """
                ),
                {"membership_id": membership_id},
            )

        token = f"dev.{subject}.{tenant_id}.viewer"

        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            response = await client.get(
                "/v1/context",
                headers={
                    "Authorization": f"Bearer {token}"
                },
            )

        assert response.status_code == 403

        async with engine.begin() as connection:
            await set_tenant_context(connection, tenant_id)

            audit_row = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            actor_subject,
                            tenant_id,
                            action,
                            decision
                        FROM audit_events
                        WHERE tenant_id = :tenant_id
                          AND actor_subject = :subject
                          AND action = 'get:/v1/context'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "subject": subject,
                    },
                )
            ).mappings().first()

            assert audit_row is not None
            assert audit_row["actor_subject"] == subject
            assert audit_row["tenant_id"] == tenant_id
            assert audit_row["decision"] == "denied"

    finally:
        await engine.dispose()



@pytest.mark.asyncio
async def test_admin_api_does_not_reflect_invalid_role_details() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-0000000000b4")
    admin_subject = "error-disclosure-admin"
    hostile_role = "super_admin<script>alert(1)</script>"

    engine = create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as connection:
            admin_membership_id = await seed_tenant_user(
                connection,
                tenant_id=tenant_id,
                slug="error-disclosure-test",
                subject=admin_subject,
                role_key="super_admin",
            )

        token = f"dev.{admin_subject}.{tenant_id}.super_admin"
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            create_response = await client.post(
                "/v1/admin/members",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "subject": "hostile-probe",
                    "roles": [hostile_role],
                },
            )

            assert create_response.status_code == 400
            assert create_response.json()["detail"] == "Invalid role selection"
            assert hostile_role not in create_response.text

            patch_response = await client.patch(
                f"/v1/admin/members/{admin_membership_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "status": "active",
                    "roles": [hostile_role],
                },
            )

            assert patch_response.status_code == 400
            assert patch_response.json()["detail"] == "Invalid role selection"
            assert hostile_role not in patch_response.text

    finally:
        await engine.dispose()
