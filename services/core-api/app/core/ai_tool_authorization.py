"""Authoritative Jarvis tool-capability derivation.

The AI/model/caller never supplies granted scopes or data scope. Capabilities
are derived only from the already-resolved tenant principal and canonical
DB-backed permission assignments.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.ai_data_scope import (
    AiDataScope,
    AiDataScopeError,
    ai_data_scope_fingerprint,
    intersect_ai_data_scopes,
    parse_ai_data_scope,
    union_ai_data_scopes,
)
from app.core.permission_catalog import action_permission

AiToolName = Literal[
    "ops_kpi_query",
    "catalog_query",
    "regulatory_impact_query",
]


SCOPE_PERMISSION_KEYS = MappingProxyType(
    {
        "ops:read": action_permission(
            "ai_assistant",
            "executeOpsRead",
        ),
        "catalog:read": action_permission(
            "ai_assistant",
            "executeCatalogRead",
        ),
        "legal:read": action_permission(
            "ai_assistant",
            "executeLegalRead",
        ),
    }
)


TOOL_REQUIRED_SCOPES = MappingProxyType(
    {
        "ops_kpi_query": (
            "ops:read",
        ),
        "catalog_query": (
            "catalog:read",
        ),
        "regulatory_impact_query": (
            "catalog:read",
            "legal:read",
        ),
    }
)


class PermissionAssignmentLike(Protocol):
    key: str
    role_key: str
    scope: dict[str, Any]


class PrincipalLike(Protocol):
    subject: str
    tenant_id: UUID
    permissions: tuple[str, ...]
    permission_assignments: tuple[
        PermissionAssignmentLike,
        ...,
    ]


class AiToolAuthorizationError(RuntimeError):
    """Base class for authoritative AI tool authorization failures."""


class AiToolAccessDenied(AiToolAuthorizationError):
    def __init__(
        self,
        *,
        missing_permissions: tuple[str, ...],
    ) -> None:
        self.missing_permissions = missing_permissions
        super().__init__("ai_tool_access_denied")


class AiToolPermissionScopeUnsupported(
    AiToolAuthorizationError
):
    """A DB grant has no safely interpretable explicit AI data scope."""


class AiToolCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    actor_subject: str
    tool: AiToolName
    granted_scopes: tuple[str, ...]
    permission_keys: tuple[str, ...]
    authorizing_roles: tuple[str, ...]
    data_scope: AiDataScope
    data_scope_fingerprint: str
    authorization_fingerprint: str


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _required_permission_keys(
    tool: AiToolName,
) -> tuple[str, ...]:
    scopes = TOOL_REQUIRED_SCOPES.get(tool)

    if scopes is None:
        # Runtime callers may bypass static typing. Never infer a
        # capability for an unknown model/tool name.
        raise AiToolAuthorizationError(
            "unsupported_ai_tool"
        )

    return tuple(
        SCOPE_PERMISSION_KEYS[scope]
        for scope in scopes
    )


def derive_ai_tool_capability(
    principal: PrincipalLike,
    *,
    tool: AiToolName,
) -> AiToolCapability:
    """Derive exact tool and data scopes from DB-backed assignments.

    Security invariants:
    - caller/model-provided granted scopes are not accepted;
    - every tool scope maps to one canonical application permission;
    - permission presence must agree with DB-backed assignments;
    - every required assignment must carry the explicit versioned AI data
      scope contract; empty/unknown/wildcard scope never means global access;
    - roles granting the same permission are additive (store union);
    - independently required permissions are restrictive (store intersection);
    - the effective data scope is bound into the authorization fingerprint.
    """

    required_scopes = TOOL_REQUIRED_SCOPES.get(tool)

    if required_scopes is None:
        raise AiToolAuthorizationError(
            "unsupported_ai_tool"
        )

    required_permissions = (
        _required_permission_keys(tool)
    )

    principal_permissions = {
        str(permission).strip()
        for permission in principal.permissions
        if str(permission).strip()
    }

    missing = tuple(
        sorted(
            permission
            for permission in required_permissions
            if permission
            not in principal_permissions
        )
    )

    if missing:
        raise AiToolAccessDenied(
            missing_permissions=missing,
        )

    assignments_by_key: dict[
        str,
        list[PermissionAssignmentLike],
    ] = {}

    for assignment in (
        principal.permission_assignments
    ):
        assignments_by_key.setdefault(
            assignment.key,
            [],
        ).append(assignment)

    authorizing_roles: set[str] = set()
    permission_data_scopes: list[AiDataScope] = []

    for permission in required_permissions:
        assignments = assignments_by_key.get(
            permission,
            [],
        )

        if not assignments:
            # principal.permissions is a convenience projection only.
            # Authorization is anchored to resolved DB assignments.
            raise AiToolAccessDenied(
                missing_permissions=(
                    permission,
                ),
            )

        assignment_scopes: list[AiDataScope] = []

        for assignment in assignments:
            role_key = str(
                assignment.role_key
            ).strip()

            if not role_key:
                raise AiToolAuthorizationError(
                    "invalid_ai_tool_authorizing_role"
                )

            try:
                assignment_scopes.append(
                    parse_ai_data_scope(
                        assignment.scope
                    )
                )
            except AiDataScopeError as exc:
                # The persisted assignment is server-authoritative. A bad
                # record is an authorization denial, never a widening default.
                raise AiToolPermissionScopeUnsupported(
                    "scoped_ai_tool_permission_unsupported"
                ) from exc

            authorizing_roles.add(role_key)

        try:
            permission_data_scopes.append(
                union_ai_data_scopes(
                    assignment_scopes
                )
            )
        except AiDataScopeError as exc:
            raise AiToolPermissionScopeUnsupported(
                "scoped_ai_tool_permission_unsupported"
            ) from exc

    try:
        data_scope = intersect_ai_data_scopes(
            permission_data_scopes
        )
    except AiDataScopeError as exc:
        raise AiToolPermissionScopeUnsupported(
            "scoped_ai_tool_permission_unsupported"
        ) from exc

    data_scope_fingerprint = (
        ai_data_scope_fingerprint(data_scope)
    )

    granted_scopes = tuple(
        sorted(required_scopes)
    )

    permission_keys = tuple(
        sorted(required_permissions)
    )

    roles = tuple(
        sorted(authorizing_roles)
    )

    fingerprint_payload: dict[str, object] = {
        "tenant_id": str(principal.tenant_id),
        "actor_subject": principal.subject,
        "tool": tool,
        "granted_scopes": granted_scopes,
        "permission_keys": permission_keys,
        "authorizing_roles": roles,
        "data_scope": data_scope.model_dump(
            mode="json"
        ),
        "data_scope_fingerprint": (
            data_scope_fingerprint
        ),
    }

    return AiToolCapability(
        tenant_id=principal.tenant_id,
        actor_subject=principal.subject,
        tool=tool,
        granted_scopes=granted_scopes,
        permission_keys=permission_keys,
        authorizing_roles=roles,
        data_scope=data_scope,
        data_scope_fingerprint=(
            data_scope_fingerprint
        ),
        authorization_fingerprint=(
            _fingerprint(
                fingerprint_payload
            )
        ),
    )
