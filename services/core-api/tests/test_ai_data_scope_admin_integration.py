from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.ai_data_scope_admin as admin_store
from app.core.ai_data_scope import AiDataScope
from app.core.ai_data_scope_admin import (
    AiDataScopeAssignmentConflict,
    AiDataScopeAssignmentNotFound,
    list_ai_data_scope_assignments,
    permission_scope_record_fingerprint,
    update_ai_data_scope_assignment,
)
from app.core.ai_tool_authorization import SCOPE_PERMISSION_KEYS
from app.core.config import get_settings

OPS_PERMISSION = SCOPE_PERMISSION_KEYS["ops:read"]


async def set_tenant_context(connection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def seed_tenant(
    connection,
    *,
    tenant_id: UUID,
    slug: str,
) -> None:
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
                :slug,
                'active'
            )
            ON CONFLICT (id) DO UPDATE SET
                slug = EXCLUDED.slug,
                display_name = EXCLUDED.display_name,
                status = 'active'
            """
        ),
        {
            "tenant_id": tenant_id,
            "slug": slug,
        },
    )
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
                'super_admin',
                'Super Admin',
                true
            )
            ON CONFLICT (tenant_id, key) DO UPDATE SET
                name = EXCLUDED.name,
                is_system = true
            """
        ),
        {"tenant_id": tenant_id},
    )
    await connection.execute(
        text(
            """
            INSERT INTO role_permissions (
                tenant_id,
                role_id,
                permission_key,
                scope
            )
            SELECT
                :tenant_id,
                r.id,
                :permission_key,
                '{}'::jsonb
            FROM roles AS r
            WHERE r.tenant_id = :tenant_id
              AND r.key = 'super_admin'
            ON CONFLICT (
                tenant_id,
                role_id,
                permission_key
            ) DO UPDATE SET scope = '{}'::jsonb
            """
        ),
        {
            "tenant_id": tenant_id,
            "permission_key": OPS_PERMISSION,
        },
    )


@pytest.mark.asyncio
async def test_scope_update_is_tenant_bound_concurrency_safe_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit events are intentionally append-only and hold a RESTRICT FK to
    # tenants. Never weaken that production invariant merely to clean test
    # rows. Use unique tenant identities so repeated runs cannot collide in a
    # dedicated test database.
    tenant_a = uuid4()
    tenant_b = uuid4()
    slug_a = f"ai-scope-admin-a-{tenant_a.hex}"
    slug_b = f"ai-scope-admin-b-{tenant_b.hex}"

    engine = create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as connection:
            await seed_tenant(
                connection,
                tenant_id=tenant_a,
                slug=slug_a,
            )
            await seed_tenant(
                connection,
                tenant_id=tenant_b,
                slug=slug_b,
            )

        records = await list_ai_data_scope_assignments(
            tenant_id=str(tenant_a),
            permission_keys=(OPS_PERMISSION,),
        )
        assert len(records) == 1
        assert records[0].role_key == "super_admin"
        assert records[0].raw_scope == {}

        initial_fingerprint = records[0].record_fingerprint
        assert initial_fingerprint == permission_scope_record_fingerprint({})

        updated = await update_ai_data_scope_assignment(
            tenant_id=str(tenant_a),
            role_key="super_admin",
            permission_key=OPS_PERMISSION,
            expected_record_fingerprint=initial_fingerprint,
            data_scope=AiDataScope(
                version=1,
                store_names=("Fulya",),
            ),
            actor_subject="admin-1",
            request_id="scope-update-1",
        )

        assert updated.changed is True
        assert updated.data_scope.store_names == ("Fulya",)
        assert updated.record_fingerprint != initial_fingerprint

        async with engine.begin() as connection:
            await set_tenant_context(connection, tenant_a)
            scope_a = await connection.scalar(
                text(
                    """
                    SELECT rp.scope
                    FROM role_permissions AS rp
                    JOIN roles AS r
                      ON r.tenant_id = rp.tenant_id
                     AND r.id = rp.role_id
                    WHERE rp.tenant_id = :tenant_id
                      AND r.key = 'super_admin'
                      AND rp.permission_key = :permission_key
                    """
                ),
                {
                    "tenant_id": tenant_a,
                    "permission_key": OPS_PERMISSION,
                },
            )
            audit = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            action,
                            resource_type,
                            resource_id,
                            request_id,
                            data
                        FROM audit_events
                        WHERE tenant_id = :tenant_id
                          AND action = 'ai_data_scope_changed'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_a},
                )
            ).mappings().first()

        async with engine.begin() as connection:
            await set_tenant_context(connection, tenant_b)
            scope_b = await connection.scalar(
                text(
                    """
                    SELECT rp.scope
                    FROM role_permissions AS rp
                    JOIN roles AS r
                      ON r.tenant_id = rp.tenant_id
                     AND r.id = rp.role_id
                    WHERE rp.tenant_id = :tenant_id
                      AND r.key = 'super_admin'
                      AND rp.permission_key = :permission_key
                    """
                ),
                {
                    "tenant_id": tenant_b,
                    "permission_key": OPS_PERMISSION,
                },
            )

        assert scope_a == {
            "ai_data_scope": {
                "version": 1,
                "store_names": ["Fulya"],
            }
        }
        assert scope_b == {}
        assert audit is not None
        assert audit["resource_type"] == "role_permission"
        assert audit["request_id"] == "scope-update-1"
        serialized_audit = json.dumps(
            audit["data"],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert "Fulya" not in serialized_audit
        assert "new_record_fingerprint" in serialized_audit
        assert "new_store_count" in serialized_audit

        with pytest.raises(AiDataScopeAssignmentConflict):
            await update_ai_data_scope_assignment(
                tenant_id=str(tenant_a),
                role_key="super_admin",
                permission_key=OPS_PERMISSION,
                expected_record_fingerprint=initial_fingerprint,
                data_scope=AiDataScope(
                    version=1,
                    store_names=("Anka",),
                ),
                actor_subject="admin-1",
                request_id="scope-update-stale",
            )

        # Scope administration cannot create a missing permission assignment.
        with pytest.raises(AiDataScopeAssignmentNotFound):
            await update_ai_data_scope_assignment(
                tenant_id=str(tenant_a),
                role_key="viewer",
                permission_key=OPS_PERMISSION,
                expected_record_fingerprint=initial_fingerprint,
                data_scope=AiDataScope(
                    version=1,
                    store_names=("Fulya",),
                ),
                actor_subject="admin-1",
                request_id="scope-update-missing",
            )

        current_records = await list_ai_data_scope_assignments(
            tenant_id=str(tenant_a),
            permission_keys=(OPS_PERMISSION,),
        )
        current = current_records[0]

        async def fail_audit(*args, **kwargs) -> None:
            del args, kwargs
            raise RuntimeError("audit write failed")

        monkeypatch.setattr(
            admin_store,
            "_write_scope_change_audit_in_transaction",
            fail_audit,
        )

        with pytest.raises(RuntimeError, match="audit write failed"):
            await update_ai_data_scope_assignment(
                tenant_id=str(tenant_a),
                role_key="super_admin",
                permission_key=OPS_PERMISSION,
                expected_record_fingerprint=current.record_fingerprint,
                data_scope=AiDataScope(
                    version=1,
                    store_names=("Anka",),
                ),
                actor_subject="admin-1",
                request_id="scope-update-audit-fail",
            )

        # The UPDATE and audit INSERT share engine.begin(); an audit failure
        # must roll the authorization change back.
        after_failure = await list_ai_data_scope_assignments(
            tenant_id=str(tenant_a),
            permission_keys=(OPS_PERMISSION,),
        )
        assert after_failure[0].raw_scope == scope_a

    finally:
        await engine.dispose()
