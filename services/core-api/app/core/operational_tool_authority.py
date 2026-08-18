"""Master 34: cross-module Jarvis tool authority composed with AI grants.

Operational module permissions are entitlements, never a replacement for the
canonical AI data-scope authority. If a module permission carries an explicit
``ai_data_scope`` contract, it may only narrow the already-authorized base AI
scope. Unknown/non-empty scope contracts fail closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from app.core.ai_data_scope import (
    AiDataScope,
    AiDataScopeError,
    ai_data_scope_fingerprint,
    intersect_ai_data_scopes,
    parse_ai_data_scope,
    union_ai_data_scopes,
)
from app.core.ai_tool_authorization import (
    AiToolAccessDenied,
    AiToolPermissionScopeUnsupported,
    PrincipalLike,
    derive_ai_tool_capability,
)
from app.core.permission_catalog import module_permission

OperationalToolName = Literal[
    "glossary_lookup",
    "field_read",
    "workforce_read",
    "inventory_read",
    "planogram_read",
    "dockos_read",
    "budget_read",
    "academy_read",
    "insight_read",
]


@dataclass(frozen=True)
class OperationalToolSpec:
    name: OperationalToolName
    module: str
    base_ai_tool: Literal["ops_kpi_query", "catalog_query"]
    required_module_permission: str
    risk: Literal["read_only"] = "read_only"


def _spec(
    name: OperationalToolName,
    module: str,
    base: Literal["ops_kpi_query", "catalog_query"] = "ops_kpi_query",
) -> OperationalToolSpec:
    return OperationalToolSpec(
        name=name,
        module=module,
        base_ai_tool=base,
        required_module_permission=module_permission(module),
    )


OPERATIONAL_TOOL_REGISTRY = MappingProxyType(
    {
        "glossary_lookup": _spec("glossary_lookup", "jarvis", "catalog_query"),
        "field_read": _spec("field_read", "field_intelligence"),
        "workforce_read": _spec("workforce_read", "workforce"),
        "inventory_read": _spec("inventory_read", "inventory"),
        "planogram_read": _spec("planogram_read", "planogram"),
        "dockos_read": _spec("dockos_read", "dockos"),
        "budget_read": _spec("budget_read", "budget"),
        "academy_read": _spec("academy_read", "academy", "catalog_query"),
        "insight_read": _spec("insight_read", "insight"),
    }
)


@dataclass(frozen=True)
class OperationalToolCapability:
    tool: OperationalToolName
    module: str
    tenant_id: str
    actor_subject: str
    data_scope: AiDataScope
    data_scope_fingerprint: str
    module_scope_fingerprint: str
    base_authorization_fingerprint: str
    authorization_fingerprint: str


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _module_scope(
    assignments: list[object],
    *,
    base_scope: AiDataScope,
) -> tuple[AiDataScope, str]:
    explicit_scopes: list[AiDataScope] = []
    entitlement_roles: list[str] = []

    for assignment in assignments:
        role_key = str(getattr(assignment, "role_key", "")).strip()
        if not role_key:
            raise AiToolAccessDenied(missing_permissions=("invalid_module_role",))
        entitlement_roles.append(role_key)

        raw_scope = getattr(assignment, "scope", None)
        if not raw_scope:
            continue
        try:
            explicit_scopes.append(parse_ai_data_scope(raw_scope))
        except AiDataScopeError as exc:
            raise AiToolPermissionScopeUnsupported(
                "operational_module_scope_unsupported"
            ) from exc

    if not explicit_scopes:
        return base_scope, _fingerprint(
            {
                "mode": "entitlement_only",
                "roles": sorted(set(entitlement_roles)),
            }
        )

    try:
        module_scope = union_ai_data_scopes(explicit_scopes)
        effective_scope = intersect_ai_data_scopes((base_scope, module_scope))
    except AiDataScopeError as exc:
        raise AiToolPermissionScopeUnsupported(
            "operational_module_scope_does_not_overlap_ai_scope"
        ) from exc

    return effective_scope, ai_data_scope_fingerprint(module_scope)


def derive_operational_tool_capability(
    principal: PrincipalLike,
    *,
    tool: OperationalToolName,
) -> OperationalToolCapability:
    spec = OPERATIONAL_TOOL_REGISTRY.get(tool)
    if spec is None:
        raise AiToolAccessDenied(missing_permissions=("unsupported_operational_tool",))

    principal_permissions = set(principal.permissions)
    if spec.required_module_permission not in principal_permissions:
        raise AiToolAccessDenied(
            missing_permissions=(spec.required_module_permission,)
        )

    module_assignments = [
        assignment
        for assignment in principal.permission_assignments
        if assignment.key == spec.required_module_permission
    ]
    if not module_assignments:
        raise AiToolAccessDenied(
            missing_permissions=(spec.required_module_permission,)
        )

    base = derive_ai_tool_capability(principal, tool=spec.base_ai_tool)
    effective_scope, module_scope_fingerprint = _module_scope(
        module_assignments,
        base_scope=base.data_scope,
    )
    effective_scope_fingerprint = ai_data_scope_fingerprint(effective_scope)

    payload = {
        "tool": tool,
        "module": spec.module,
        "tenant_id": str(principal.tenant_id),
        "actor_subject": principal.subject,
        "module_permission": spec.required_module_permission,
        "module_roles": sorted(
            {str(assignment.role_key).strip() for assignment in module_assignments}
        ),
        "module_scope_fingerprint": module_scope_fingerprint,
        "base_authorization_fingerprint": base.authorization_fingerprint,
        "data_scope_fingerprint": effective_scope_fingerprint,
    }
    return OperationalToolCapability(
        tool=tool,
        module=spec.module,
        tenant_id=str(principal.tenant_id),
        actor_subject=principal.subject,
        data_scope=effective_scope,
        data_scope_fingerprint=effective_scope_fingerprint,
        module_scope_fingerprint=module_scope_fingerprint,
        base_authorization_fingerprint=base.authorization_fingerprint,
        authorization_fingerprint=_fingerprint(payload),
    )
