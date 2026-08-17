from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class GovernedMetric:
    key:str; family:str; formula_version:str; glossary_concept_id:str; source_contract:str; production_ready:bool

KPI_FAMILY_ORDER=('orders','nsfr_pfr_refund','prep_picking_otp_putaway','inventory','workforce','dock_budget')

def can_activate_family(*,family:str,orders_v2_ready:bool,metrics:tuple[GovernedMetric,...])->bool:
    if family not in KPI_FAMILY_ORDER: return False
    if family!='orders' and not orders_v2_ready: return False
    members=[m for m in metrics if m.family==family]
    return bool(members) and all(m.production_ready and m.formula_version and m.glossary_concept_id and m.source_contract for m in members)
