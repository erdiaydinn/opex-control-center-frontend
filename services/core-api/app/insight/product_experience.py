from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class MetricProvenance:
    metric_key:str; formula_version:str; source_contract:str; glossary_concept_id:str; observed_at:str
@dataclass(frozen=True)
class InsightCard:
    metric_key:str; value:float; trend:tuple[float,...]; explanation:str; provenance:MetricProvenance; root_causes:tuple[str,...]; anomaly:bool

def build_insight_card(*,metric_key:str,value:float,trend:tuple[float,...],explanation:str,provenance:MetricProvenance,root_causes:tuple[str,...]=(),anomaly:bool=False)->InsightCard:
    if metric_key!=provenance.metric_key or not provenance.formula_version or not provenance.source_contract or not provenance.glossary_concept_id:
        raise ValueError('Insight metric provenance is incomplete or mismatched')
    if not explanation.strip(): raise ValueError('Insight explanation required')
    return InsightCard(metric_key,value,trend,explanation,provenance,root_causes,anomaly)
