from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

EvidenceClass=Literal['REPOSITORY','SYNTHETIC','REAL_PRODUCTION_READONLY']
REQUIRED=('authorized_readonly_identity','information_schema_observation','entity_id_discriminator','cross_tenant_zero_leak','schema_attestation','human_release_deploy_promotion')

@dataclass(frozen=True)
class ProductionEvidence:
    key:str; evidence_class:EvidenceClass; passed:bool; provenance:str; approver:str

def orders_v2_production_ready(records:tuple[ProductionEvidence,...])->tuple[bool,tuple[str,...]]:
    by_key={r.key:r for r in records}; blockers=[]
    for key in REQUIRED:
        r=by_key.get(key)
        if r is None: blockers.append(f'{key}:missing'); continue
        if not r.passed: blockers.append(f'{key}:failed'); continue
        if r.evidence_class!='REAL_PRODUCTION_READONLY': blockers.append(f'{key}:not_live_production_evidence'); continue
        if not r.provenance.strip() or not r.approver.strip(): blockers.append(f'{key}:incomplete_provenance')
    return not blockers,tuple(blockers)
