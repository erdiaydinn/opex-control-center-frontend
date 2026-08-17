"""Master 34: cross-module Jarvis tool authority composed with existing AI grants."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from app.core.ai_tool_authorization import AiToolAccessDenied, PrincipalLike, derive_ai_tool_capability
from app.core.permission_catalog import module_permission

OperationalToolName = Literal[
    "glossary_lookup","field_read","workforce_read","inventory_read","planogram_read",
    "dockos_read","budget_read","academy_read","insight_read",
]

@dataclass(frozen=True)
class OperationalToolSpec:
    name: OperationalToolName
    module: str
    base_ai_tool: Literal["ops_kpi_query","catalog_query"]
    required_module_permission: str
    risk: Literal["read_only"] = "read_only"


def _spec(name: OperationalToolName, module: str, base: Literal["ops_kpi_query","catalog_query"]="ops_kpi_query") -> OperationalToolSpec:
    return OperationalToolSpec(name,module,base,module_permission(module))

OPERATIONAL_TOOL_REGISTRY = MappingProxyType({
    "glossary_lookup": _spec("glossary_lookup","jarvis","catalog_query"),
    "field_read": _spec("field_read","field_intelligence"),
    "workforce_read": _spec("workforce_read","workforce"),
    "inventory_read": _spec("inventory_read","inventory"),
    "planogram_read": _spec("planogram_read","planogram"),
    "dockos_read": _spec("dockos_read","dockos"),
    "budget_read": _spec("budget_read","budget"),
    "academy_read": _spec("academy_read","academy","catalog_query"),
    "insight_read": _spec("insight_read","insight"),
})

@dataclass(frozen=True)
class OperationalToolCapability:
    tool: OperationalToolName
    module: str
    tenant_id: str
    actor_subject: str
    data_scope_fingerprint: str
    base_authorization_fingerprint: str
    authorization_fingerprint: str


def derive_operational_tool_capability(principal: PrincipalLike, *, tool: OperationalToolName) -> OperationalToolCapability:
    spec=OPERATIONAL_TOOL_REGISTRY.get(tool)
    if spec is None:
        raise AiToolAccessDenied(missing_permissions=("unsupported_operational_tool",))
    if spec.required_module_permission not in set(principal.permissions):
        raise AiToolAccessDenied(missing_permissions=(spec.required_module_permission,))
    module_assignments=[a for a in principal.permission_assignments if a.key==spec.required_module_permission]
    if not module_assignments or any(not str(a.role_key).strip() for a in module_assignments):
        raise AiToolAccessDenied(missing_permissions=(spec.required_module_permission,))
    base=derive_ai_tool_capability(principal,tool=spec.base_ai_tool)
    payload={"tool":tool,"module":spec.module,"tenant_id":str(principal.tenant_id),"actor":principal.subject,"module_permission":spec.required_module_permission,"module_roles":sorted({a.role_key for a in module_assignments}),"base_authorization_fingerprint":base.authorization_fingerprint,"data_scope_fingerprint":base.data_scope_fingerprint}
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return OperationalToolCapability(tool,spec.module,str(principal.tenant_id),principal.subject,base.data_scope_fingerprint,base.authorization_fingerprint,fingerprint)
