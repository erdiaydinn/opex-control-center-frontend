from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class AiSubstrateContract:
    frozen_pr:int
    capabilities:frozenset[str]
    consumers:frozenset[str]
    source_provenance_required:bool
    tenant_authorization_required:bool
    promotion_requires_eval:bool
    promotion_requires_human_approval:bool


def load_substrate_contract(path:Path)->AiSubstrateContract:
    d=json.loads(path.read_text(encoding='utf-8'))
    if d.get('schema_version')!=1: raise ValueError('unsupported AI substrate schema')
    frozen=d['frozen_baseline']
    if frozen.get('pull_request')!=15 or frozen.get('mutable') is not False: raise ValueError('AI Core frozen PR #15 contract changed')
    boundaries=d['truth_boundaries']
    required_true=('promotion_requires_eval','promotion_requires_human_approval','source_provenance_required','tenant_authorization_required')
    if not all(boundaries.get(k) is True for k in required_true): raise ValueError('AI Core promotion/source/tenant gate weakened')
    if boundaries.get('self_modify_production_weights') is not False or boundaries.get('synthetic_is_production_evidence') is not False: raise ValueError('AI Core production truth boundary weakened')
    return AiSubstrateContract(15,frozenset(d['capabilities']),frozenset(d['consumer_modules']),True,True,True,True)


def authorize_consumer(contract:AiSubstrateContract,*,module:str,tenant_authorized:bool,provenance_bound:bool)->bool:
    return module in contract.consumers and tenant_authorized and provenance_bound
