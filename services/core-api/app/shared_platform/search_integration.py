from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping,Sequence
from app.shared_platform.contracts import IntegrationContract,SearchDocument

@dataclass(frozen=True)
class SearchPrincipal:
    permissions:frozenset[str]

def visible_search_documents(principal:SearchPrincipal,documents:Sequence[SearchDocument])->tuple[SearchDocument,...]:
    return tuple(d for d in documents if d.permission_key in principal.permissions and d.provenance)

def validate_inbound_payload(contract:IntegrationContract,payload:Mapping[str,object])->tuple[bool,tuple[str,...]]:
    required=tuple(str(x) for x in contract.validation_policy.get('required_fields',()))
    allowed=contract.validation_policy.get('allowed_fields')
    errors=[]
    for key in required:
        if key not in payload or payload[key] in (None,''): errors.append(f'{key}:required')
    if isinstance(allowed,(list,tuple)):
        extras=sorted(set(payload)-set(str(x) for x in allowed))
        errors.extend(f'{key}:unexpected' for key in extras)
    if 'tenant_id' in payload: errors.append('tenant_id:payload_authority_forbidden')
    return not errors,tuple(errors)
