from dataclasses import dataclass
from uuid import UUID
import pytest
from app.core.ai_tool_authorization import AiToolAccessDenied,SCOPE_PERMISSION_KEYS
from app.core.operational_tool_authority import OPERATIONAL_TOOL_REGISTRY,derive_operational_tool_capability
from app.core.permission_catalog import module_permission

TENANT=UUID('11111111-1111-4111-8111-111111111111')
@dataclass(frozen=True)
class Assignment:
    key:str; role_key:str; scope:dict[str,object]
@dataclass(frozen=True)
class Principal:
    subject:str; tenant_id:UUID; permissions:tuple[str,...]; permission_assignments:tuple[Assignment,...]

def scope(): return {'ai_data_scope':{'version':1,'store_names':['Fulya']}}
def principal(module:str,*,assignment=True):
    ops=SCOPE_PERMISSION_KEYS['ops:read']; mod=module_permission(module)
    assignments=[Assignment(ops,'ops_reader',scope())]
    if assignment: assignments.append(Assignment(mod,'module_reader',{}))
    return Principal('user',TENANT,(ops,mod),tuple(assignments))

def test_registry_covers_master34_modules():
    assert set(OPERATIONAL_TOOL_REGISTRY)=={'glossary_lookup','field_read','workforce_read','inventory_read','planogram_read','dockos_read','budget_read','academy_read','insight_read'}

def test_budget_tool_requires_both_ai_scope_and_budget_entitlement():
    cap=derive_operational_tool_capability(principal('budget'),tool='budget_read')
    assert cap.module=='budget' and len(cap.authorization_fingerprint)==64 and len(cap.data_scope_fingerprint)==64
    with pytest.raises(AiToolAccessDenied): derive_operational_tool_capability(principal('budget',assignment=False),tool='budget_read')

def test_cross_module_permission_cannot_be_reused():
    with pytest.raises(AiToolAccessDenied): derive_operational_tool_capability(principal('academy'),tool='budget_read')
