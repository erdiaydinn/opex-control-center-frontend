"""Tenant-scoped administrative persistence for Jarvis data scopes.

This module does not create permissions. It can only replace the scope on an
existing role_permissions assignment, with optimistic concurrency and an audit
record committed in the same database transaction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.ai_data_scope import (
    AiDataScope,
    AiDataScopeError,
    parse_ai_data_scope,
)
from app.core.resources import engine

SHA256_HEX_LENGTH = 64


class AiDataScopeAdminError(RuntimeError):
    """Base error for administrative AI data-scope persistence."""


class AiDataScopeAssignmentNotFound(AiDataScopeAdminError):
    """The requested role already lacks the requested AI permission."""


class AiDataScopeAssignmentConflict(AiDataScopeAdminError):
    """The assignment changed after the administrator read it."""


@dataclass(frozen=True)
class AiDataScopeAssignmentRecord:
    role_key: str
    role_name: str
    is_system: bool
    permission_key: str
    raw_scope: dict[str, Any]
    record_fingerprint: str


@dataclass(frozen=True)
class AiDataScopeAssignmentUpdate:
    role_key: str
    permission_key: str
    record_fingerprint: str
    data_scope: AiDataScope
    changed: bool


def permission_scope_record_fingerprint(
    scope: Mapping[str, Any],
) -> str:
    """Fingerprint the exact persisted JSONB authorization record."""

    encoded = json.dumps(
        dict(scope),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def role_permission_scope_payload(
    data_scope: AiDataScope,
) -> dict[str, object]:
    return {
        "ai_data_scope": data_scope.model_dump(
            mode="json"
        )
    }


def _scope_store_count(scope: Mapping[str, Any]) -> int | None:
    try:
        parsed = parse_ai_data_scope(scope)
    except AiDataScopeError:
        return None
    return len(parsed.store_names)


async def list_ai_data_scope_assignments(
    *,
    tenant_id: str,
    permission_keys: Sequence[str],
) -> tuple[AiDataScopeAssignmentRecord, ...]:
    if not permission_keys:
        return ()

    statement = text(
        """
        SELECT
            r.key AS role_key,
            r.name AS role_name,
            r.is_system,
            rp.permission_key,
            rp.scope
        FROM role_permissions AS rp
        JOIN roles AS r
          ON r.tenant_id = rp.tenant_id
         AND r.id = rp.role_id
        WHERE rp.tenant_id = CAST(:tenant_id AS UUID)
          AND rp.permission_key = ANY(
              CAST(:permission_keys AS varchar[])
          )
        ORDER BY r.key ASC, rp.permission_key ASC
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )
        result = await connection.execute(
            statement,
            {
                "tenant_id": tenant_id,
                "permission_keys": list(permission_keys),
            },
        )
        rows = result.mappings().all()

    return tuple(
        AiDataScopeAssignmentRecord(
            role_key=str(row["role_key"]),
            role_name=str(row["role_name"]),
            is_system=bool(row["is_system"]),
            permission_key=str(row["permission_key"]),
            raw_scope=dict(row["scope"] or {}),
            record_fingerprint=permission_scope_record_fingerprint(
                dict(row["scope"] or {})
            ),
        )
        for row in rows
    )


async def _write_scope_change_audit_in_transaction(
    connection: AsyncConnection,
    *,
    tenant_id: str,
    actor_subject: str,
    request_id: str,
    role_key: str,
    permission_key: str,
    old_record_fingerprint: str,
    new_record_fingerprint: str,
    old_store_count: int | None,
    new_store_count: int,
) -> None:
    data = {
        "method": "PUT",
        "path": (
            "/v1/admin/ai-data-scopes/"
            f"{role_key}/{permission_key}"
        ),
        "status_code": 200,
        "metadata": {
            "role_key": role_key,
            "permission_key": permission_key,
            "old_record_fingerprint": old_record_fingerprint,
            "new_record_fingerprint": new_record_fingerprint,
            "old_store_count": old_store_count,
            "new_store_count": new_store_count,
        },
    }

    await connection.execute(
        text(
            """
            INSERT INTO audit_events (
                tenant_id,
                actor_subject,
                action,
                resource_type,
                resource_id,
                decision,
                request_id,
                data
            )
            VALUES (
                CAST(:tenant_id AS UUID),
                :actor_subject,
                'ai_data_scope_changed',
                'role_permission',
                :resource_id,
                'allowed',
                :request_id,
                CAST(:data AS JSONB)
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "actor_subject": actor_subject,
            "resource_id": f"{role_key}:{permission_key}",
            "request_id": request_id,
            "data": json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    )


async def update_ai_data_scope_assignment(
    *,
    tenant_id: str,
    role_key: str,
    permission_key: str,
    expected_record_fingerprint: str,
    data_scope: AiDataScope,
    actor_subject: str,
    request_id: str,
) -> AiDataScopeAssignmentUpdate:
    """Atomically replace an existing permission scope and record the audit."""

    if (
        len(expected_record_fingerprint) != SHA256_HEX_LENGTH
        or any(
            char not in "0123456789abcdef"
            for char in expected_record_fingerprint
        )
    ):
        raise ValueError(
            "expected_record_fingerprint must be lowercase SHA-256"
        )

    new_scope = role_permission_scope_payload(data_scope)
    new_record_fingerprint = permission_scope_record_fingerprint(
        new_scope
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            text(
                """
                SELECT
                    rp.id,
                    rp.scope,
                    r.key AS role_key
                FROM role_permissions AS rp
                JOIN roles AS r
                  ON r.tenant_id = rp.tenant_id
                 AND r.id = rp.role_id
                WHERE rp.tenant_id = CAST(:tenant_id AS UUID)
                  AND r.key = :role_key
                  AND rp.permission_key = :permission_key
                FOR UPDATE OF rp
                """
            ),
            {
                "tenant_id": tenant_id,
                "role_key": role_key,
                "permission_key": permission_key,
            },
        )
        row = result.mappings().first()

        if row is None:
            raise AiDataScopeAssignmentNotFound(
                "AI permission assignment not found"
            )

        old_scope = dict(row["scope"] or {})
        old_record_fingerprint = (
            permission_scope_record_fingerprint(old_scope)
        )

        if old_record_fingerprint != expected_record_fingerprint:
            raise AiDataScopeAssignmentConflict(
                "AI data scope assignment changed"
            )

        if old_record_fingerprint == new_record_fingerprint:
            return AiDataScopeAssignmentUpdate(
                role_key=role_key,
                permission_key=permission_key,
                record_fingerprint=new_record_fingerprint,
                data_scope=data_scope,
                changed=False,
            )

        await connection.execute(
            text(
                """
                UPDATE role_permissions
                SET scope = CAST(:scope AS JSONB)
                WHERE id = CAST(:assignment_id AS UUID)
                  AND tenant_id = CAST(:tenant_id AS UUID)
                """
            ),
            {
                "assignment_id": str(row["id"]),
                "tenant_id": tenant_id,
                "scope": json.dumps(
                    new_scope,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        )

        await _write_scope_change_audit_in_transaction(
            connection,
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            request_id=request_id,
            role_key=role_key,
            permission_key=permission_key,
            old_record_fingerprint=old_record_fingerprint,
            new_record_fingerprint=new_record_fingerprint,
            old_store_count=_scope_store_count(old_scope),
            new_store_count=len(data_scope.store_names),
        )

    return AiDataScopeAssignmentUpdate(
        role_key=role_key,
        permission_key=permission_key,
        record_fingerprint=new_record_fingerprint,
        data_scope=data_scope,
        changed=True,
    )
