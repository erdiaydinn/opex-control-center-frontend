from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

KpiReviewState = Literal["reviewed", "blocked_schema_verification"]


@dataclass(frozen=True)
class KpiDefinition:
    metric: str
    query_id: str | None
    review_state: KpiReviewState
    source_table: str | None
    value_semantics: str
    schema_contract_id: str | None = None
    semantic_contract_id: str | None = None
    schema_contract_fingerprint: str | None = None
    semantic_contract_fingerprint: str | None = None
    query_template_fingerprint: str | None = None
    registry_promotion_fingerprint: str | None = None
    promotion_schema_fingerprint: str | None = None
    review_artifact_fingerprint: str | None = None
    registry_binding_fingerprint: str | None = None
    legacy_bootstrap: bool = False
    blocked_reason: str | None = None

    @property
    def executable(self) -> bool:
        promotion_lineage_ready = self.legacy_bootstrap or (
            bool(self.registry_promotion_fingerprint)
            and bool(self.promotion_schema_fingerprint)
            and bool(self.review_artifact_fingerprint)
        )
        return (
            self.review_state == "reviewed"
            and bool(self.query_id)
            and bool(self.schema_contract_id)
            and bool(self.semantic_contract_id)
            and bool(self.schema_contract_fingerprint)
            and bool(self.semantic_contract_fingerprint)
            and bool(self.query_template_fingerprint)
            and bool(self.registry_binding_fingerprint)
            and promotion_lineage_ready
        )


# New executable KPIs must pin exact schema/semantic/query contracts plus the sealed
# promotion decision, the schema fingerprint reviewed by that decision, the exact
# production review artifact, and the final composite binding. Orders is the sole
# explicit legacy bootstrap exception; it still pins every applicable contract/template
# fingerprint so drift fails closed.
KPI_REGISTRY: dict[str, KpiDefinition] = {
    "orders": KpiDefinition(
        metric="orders",
        query_id="ops.kpi.orders.v1",
        review_state="reviewed",
        source_table="curated_data_shared_coredata_business.orders",
        value_semantics="COUNT(DISTINCT order_id) grouped by local date and vendor/store",
        schema_contract_id="ops.orders.v1",
        semantic_contract_id="ops.orders.semantic.v1",
        schema_contract_fingerprint="4957415364d06a56745d29efa2423a87499727200fd94a0df34af08af5bbcaa5",
        semantic_contract_fingerprint="f804ab70c43237caf607e78b387e959a7476526219f222a579fd4f8476c13658",
        query_template_fingerprint="aab639e0a69cd8cfbec992c2bc737e12679835259c09906bd7f4e98c9f91c7f4",
        registry_binding_fingerprint="ebc40cdaec8fb104c6f6957a51d98041b72efa938cbb17faffd1152ddcf0691e",
        legacy_bootstrap=True,
    ),
    "cancel_rate": KpiDefinition(metric="cancel_rate", query_id=None, review_state="blocked_schema_verification", source_table=None, value_semantics="cancelled orders / eligible orders", blocked_reason="production cancellation reason/status schema not yet pinned in this service"),
    "nsfr": KpiDefinition(metric="nsfr", query_id=None, review_state="blocked_schema_verification", source_table="report_dmart_ops_nsfr_global_overview", value_semantics="NSFR = PFR + Refund + Compensation with documented precedence rules", semantic_contract_id="ops.nsfr.semantic.v1", blocked_reason="column-level production schema and precedence mapping require explicit verification"),
    "pfr": KpiDefinition(metric="pfr", query_id=None, review_state="blocked_schema_verification", source_table="report_dmart_ops_nsfr_global_overview", value_semantics="partially fulfilled order rate", semantic_contract_id="ops.pfr.semantic.v1", blocked_reason="column-level production schema requires explicit verification"),
    "refund": KpiDefinition(metric="refund", query_id=None, review_state="blocked_schema_verification", source_table="report_dmart_ops_nsfr_global_overview", value_semantics="refund rate after PFR precedence handling", semantic_contract_id="ops.refund.semantic.v1", blocked_reason="column-level production schema and precedence mapping require explicit verification"),
    "prep": KpiDefinition(metric="prep", query_id=None, review_state="blocked_schema_verification", source_table="report__tableau_store_performance_report", value_semantics="average preparation duration", semantic_contract_id="ops.prep.semantic.v1", blocked_reason="production duration column/unit requires explicit verification"),
    "picking": KpiDefinition(metric="picking", query_id=None, review_state="blocked_schema_verification", source_table="dmart_ops_picker_individual_performance_daily", value_semantics="picking duration per order", semantic_contract_id="ops.picking.semantic.v1", blocked_reason="production aggregation and duration-unit contract require explicit verification"),
    "putaway": KpiDefinition(metric="putaway", query_id=None, review_state="blocked_schema_verification", source_table="dmart_ops_st_po_receiving_putaway_sku_details", value_semantics="putaway compliance / issue quantity according to reviewed inbound SLA", semantic_contract_id="ops.putaway.semantic.v1", blocked_reason="ST/PO SLA and city-offset fields require explicit schema verification"),
    "otp": KpiDefinition(metric="otp", query_id=None, review_state="blocked_schema_verification", source_table="report__tableau_store_performance_report", value_semantics="OTP 4.25 = 100 - late_prep_rate_percent", semantic_contract_id="ops.otp.semantic.v1", blocked_reason="late-prep source column and percent scale require explicit verification"),
    "defect": KpiDefinition(metric="defect", query_id=None, review_state="blocked_schema_verification", source_table=None, value_semantics="defect rate", blocked_reason="authoritative production defect denominator/source not yet pinned"),
}


def get_kpi_definition(metric: str) -> KpiDefinition:
    definition = KPI_REGISTRY.get(metric)
    if definition is None:
        raise ValueError(f"unknown_kpi_metric:{metric}")
    return definition


def require_executable_kpi(metric: str) -> KpiDefinition:
    definition = get_kpi_definition(metric)
    if not definition.executable:
        raise ValueError(f"metric_template_not_implemented:{metric}")
    from .kpi_registry_integrity import verify_registry_binding

    verify_registry_binding(definition)
    return definition
