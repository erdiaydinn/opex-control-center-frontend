from __future__ import annotations
from dataclasses import dataclass,field
from enum import StrEnum
from typing import Mapping

class ReleaseState(StrEnum):
    DEVELOPMENT='DEVELOPMENT'; PRODUCTION_CANDIDATE='PRODUCTION_CANDIDATE'; PILOT='PILOT'; PILOT_ACCEPTED='PILOT_ACCEPTED'; PRODUCTION_ACTIVE='PRODUCTION_ACTIVE'; STABILIZING='STABILIZING'

@dataclass(frozen=True)
class ReleaseTruth:
    repository_green:bool
    sre_items:Mapping[int,bool]
    external_items:Mapping[int,bool]
    pilot_metrics:Mapping[str,bool]=field(default_factory=dict)
    signoffs:Mapping[str,bool]=field(default_factory=dict)

REQUIRED_EXTERNAL=tuple(range(49,56)); REQUIRED_SRE=tuple(range(45,49))
PILOT_METRICS=('error_budget','task_success','latency','reconciliation','support_cases','device_issues','user_feedback','rollback_criteria')
PROD_SIGNOFFS=('security','dr','identity','real_data','module_owner')

def can_create_production_candidate(t:ReleaseTruth)->bool:
    return t.repository_green and all(t.sre_items.get(i,False) for i in REQUIRED_SRE) and all(t.external_items.get(i,False) for i in REQUIRED_EXTERNAL)

def can_accept_pilot(t:ReleaseTruth)->bool:
    return can_create_production_candidate(t) and all(t.pilot_metrics.get(k,False) for k in PILOT_METRICS)

def can_activate_production(t:ReleaseTruth,*,tenant_ids:tuple[str,...],modules:tuple[str,...])->bool:
    return can_accept_pilot(t) and bool(tenant_ids) and bool(modules) and all(t.signoffs.get(k,False) for k in PROD_SIGNOFFS)

def next_state(current:ReleaseState,t:ReleaseTruth,*,tenant_ids:tuple[str,...]=(),modules:tuple[str,...]=())->ReleaseState:
    if current==ReleaseState.DEVELOPMENT:
        if not can_create_production_candidate(t): raise ValueError('production candidate blocked by repository/SRE/external evidence')
        return ReleaseState.PRODUCTION_CANDIDATE
    if current==ReleaseState.PRODUCTION_CANDIDATE: return ReleaseState.PILOT
    if current==ReleaseState.PILOT:
        if not can_accept_pilot(t): raise ValueError('pilot acceptance evidence incomplete')
        return ReleaseState.PILOT_ACCEPTED
    if current==ReleaseState.PILOT_ACCEPTED:
        if not can_activate_production(t,tenant_ids=tenant_ids,modules=modules): raise ValueError('controlled production activation blocked')
        return ReleaseState.PRODUCTION_ACTIVE
    if current==ReleaseState.PRODUCTION_ACTIVE: return ReleaseState.STABILIZING
    raise ValueError('state transition requires explicit category-leadership iteration')

@dataclass(frozen=True)
class BenchmarkSignal:
    source:str; category:str; observed_change:str; evidence_ref:str

def category_leadership_backlog(signals:tuple[BenchmarkSignal,...])->tuple[BenchmarkSignal,...]:
    return tuple(sorted((s for s in signals if s.evidence_ref.strip()),key=lambda s:(s.category,s.source,s.observed_change)))
