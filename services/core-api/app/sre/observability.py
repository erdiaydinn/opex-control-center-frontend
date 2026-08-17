from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

@dataclass(frozen=True)
class TelemetryEvent:
    signal:str; service:str; environment:str; workflow:str; operation:str; result:str; dimensions:Mapping[str,str]

def load_observability_contract(path:Path)->dict[str,object]:
    d=json.loads(path.read_text(encoding='utf-8'))
    if d.get('schema_version')!=1: raise ValueError('unsupported observability schema')
    if len(set(d['required_signals']))!=len(d['required_signals']): raise ValueError('duplicate required signal')
    return d

def validate_telemetry_event(contract:dict[str,object],event:TelemetryEvent)->None:
    if event.signal not in contract['required_signals']: raise ValueError('unregistered telemetry signal')
    if not all((event.service,event.environment,event.workflow,event.operation,event.result)): raise ValueError('telemetry authority dimensions required')
    forbidden={str(x) for x in contract['forbidden_dimensions']}
    if forbidden & set(event.dimensions): raise ValueError('sensitive telemetry dimension forbidden')

def load_profiles(path:Path)->tuple[dict[str,object],...]:
    d=json.loads(path.read_text(encoding='utf-8'))
    profiles=tuple(d.get('profiles',()))
    keys=[p['key'] for p in profiles]
    if len(keys)!=len(set(keys)): raise ValueError('duplicate load profile')
    if any(p.get('evidence_class') in {'SYNTHETIC','REPOSITORY'} for p in profiles): raise ValueError('production-shape profile cannot be synthetic')
    return profiles
