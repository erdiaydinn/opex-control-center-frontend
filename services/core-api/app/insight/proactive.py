from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Risk=Literal['LOW','MEDIUM','HIGH']
@dataclass(frozen=True)
class GovernedSignal:
    key:str; module:str; reason:str; evidence_refs:tuple[str,...]; risk:Risk; proposed_action:str|None=None

def create_signal(*,key:str,module:str,reason:str,evidence_refs:tuple[str,...],risk:Risk,proposed_action:str|None=None)->GovernedSignal:
    if not evidence_refs or any(not r.strip() for r in evidence_refs): raise ValueError('proactive signal requires governed evidence')
    if not reason.strip(): raise ValueError('signal reason required')
    return GovernedSignal(key,module,reason,evidence_refs,risk,proposed_action)

def action_requires_approval(signal:GovernedSignal)->bool:
    return signal.proposed_action is not None and signal.risk in {'MEDIUM','HIGH'}

def auto_action_permitted(signal:GovernedSignal)->bool:
    return signal.proposed_action is not None and signal.risk=='LOW'
