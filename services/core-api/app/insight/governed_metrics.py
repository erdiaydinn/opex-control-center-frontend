"""Master 36: tenant-bound governed KPI family activation contracts."""

from __future__ import annotations

from dataclasses import dataclass

from app.jarvis.orders_v2_production_truth import OrdersV2ProductionReceipt

KPI_FAMILY_ORDER = (
    "orders",
    "nsfr_pfr_refund",
    "prep_picking_otp_putaway",
    "inventory",
    "workforce",
    "dock_budget",
)


@dataclass(frozen=True)
class GovernedMetric:
    tenant_id: str
    key: str
    family: str
    formula_version: str
    glossary_concept_id: str
    source_contract: str
    production_ready: bool


def can_activate_family(
    *,
    tenant_id: str,
    family: str,
    orders_v2_receipt: OrdersV2ProductionReceipt,
    metrics: tuple[GovernedMetric, ...],
) -> bool:
    normalized_tenant = tenant_id.strip()
    if not normalized_tenant or family not in KPI_FAMILY_ORDER:
        return False

    if not orders_v2_receipt.ready:
        return False
    if orders_v2_receipt.tenant_id != normalized_tenant:
        return False
    if not orders_v2_receipt.evidence_fingerprint.strip():
        return False

    members = tuple(
        metric
        for metric in metrics
        if metric.family == family and metric.tenant_id == normalized_tenant
    )
    if not members:
        return False

    return all(
        metric.production_ready
        and bool(metric.formula_version.strip())
        and bool(metric.glossary_concept_id.strip())
        and bool(metric.source_contract.strip())
        for metric in members
    )
