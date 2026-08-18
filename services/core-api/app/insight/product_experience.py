"""Master 37: provenance-bound Insight product contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricProvenance:
    tenant_id: str
    metric_key: str
    formula_version: str
    source_contract: str
    glossary_concept_id: str
    evidence_fingerprint: str
    observed_at: str


@dataclass(frozen=True)
class InsightCard:
    tenant_id: str
    metric_key: str
    value: float
    trend: tuple[float, ...]
    explanation: str
    provenance: MetricProvenance
    root_causes: tuple[str, ...]
    anomaly: bool


def build_insight_card(
    *,
    tenant_id: str,
    metric_key: str,
    value: float,
    trend: tuple[float, ...],
    explanation: str,
    provenance: MetricProvenance,
    root_causes: tuple[str, ...] = (),
    anomaly: bool = False,
) -> InsightCard:
    normalized_tenant = tenant_id.strip()
    if not normalized_tenant or provenance.tenant_id != normalized_tenant:
        raise ValueError("Insight metric tenant provenance is incomplete or mismatched")
    if metric_key != provenance.metric_key:
        raise ValueError("Insight metric provenance is incomplete or mismatched")
    if not all(
        (
            provenance.formula_version.strip(),
            provenance.source_contract.strip(),
            provenance.glossary_concept_id.strip(),
            provenance.evidence_fingerprint.strip(),
            provenance.observed_at.strip(),
        )
    ):
        raise ValueError("Insight metric provenance is incomplete or mismatched")
    if not explanation.strip():
        raise ValueError("Insight explanation required")

    return InsightCard(
        tenant_id=normalized_tenant,
        metric_key=metric_key,
        value=value,
        trend=trend,
        explanation=explanation,
        provenance=provenance,
        root_causes=root_causes,
        anomaly=anomaly,
    )
