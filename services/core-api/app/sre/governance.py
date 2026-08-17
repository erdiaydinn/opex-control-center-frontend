from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

EvidenceClass = Literal['REPOSITORY','SYNTHETIC','MANAGED_STAGING','REAL_ENVIRONMENT']

@dataclass(frozen=True)
class AcceptanceEvidence:
    key:str
    evidence_class:EvidenceClass
    environment:str
    measured:bool
    provenance:str


def external_gate_satisfied(evidence: AcceptanceEvidence) -> bool:
    return evidence.evidence_class in {'MANAGED_STAGING','REAL_ENVIRONMENT'} and evidence.measured and bool(evidence.provenance.strip())


def load_sre_registry(path:Path)->dict[str,object]:
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version')!=1: raise ValueError('unsupported SRE registry schema')
    services=data.get('services',[])
    keys=[item['service'] for item in services]
    if len(keys)!=len(set(keys)): raise ValueError('duplicate service ownership')
    for item in services:
        if not item.get('owner'): raise ValueError('service owner required')
        slo=item.get('slo',{})
        if not 0 < float(slo.get('availability',0)) <= 1: raise ValueError('invalid availability SLO')
    for test in data.get('production_shape_tests',[]):
        if test.get('synthetic_is_sufficient') is not False: raise ValueError('production-shape load cannot accept synthetic evidence')
    if data.get('dr_requirements',{}).get('synthetic_is_sufficient') is not False: raise ValueError('DR cannot accept synthetic evidence')
    return data
