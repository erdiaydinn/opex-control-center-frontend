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
    blocked_reason: str | None = None

    @property
    def executable(self) -> bool:
        return (
            self.review_state == "reviewed"
            and bool(self.query_id)
            and bool(self.schema_contract_id)
        )


# This registry is intentionally conservative. A metric is executable only after its
# production schema and business definition have both been reviewed. Merely knowing a
# plausible table name is not enough to expose it to the model/tool runtime.
KPI_REGISTRY: dict[str, KpiDefinition] = {
    "orders": KpiDefinition(
        metric="orders",
        query_id="ops.kpi.orders.v1",
        review_state="reviewed",
        source_table="curated_data_shared_coredata_business.orders",
        value_semantics="COUNT(DISTINCT order_id) grouped by local date and vendor/store",
        schema_contract_id="ops.orders.v1",
    ),
    "cancel_rate": KpiDefinition(
        metric="cancel_rate",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table=None,
        value_semantics="cancelled orders / eligible orders",
        blocked_reason="production cancellation reason/status schema not yet pinned in this service",
    ),
    "nsfr": KpiDefinition(
        metric="nsfr",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="report_dmart_ops_nsfr_global_overview",
        value_semantics="NSFR = PFR + Refund + Compensation with documented precedence rules",
        blocked_reason="column-level production schema and precedence mapping require explicit verification",
    ),
    "pfr": KpiDefinition(
        metric="pfr",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="report_dmart_ops_nsfr_global_overview",
        value_semantics="partially fulfilled order rate",
        blocked_reason="column-level production schema requires explicit verification",
    ),
    "refund": KpiDefinition(
        metric="refund",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="report_dmart_ops_nsfr_global_overview",
        value_semantics="refund rate after PFR precedence handling",
        blocked_reason="column-level production schema and precedence mapping require explicit verification",
    ),
    "prep": KpiDefinition(
        metric="prep",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="report__tableau_store_performance_report",
        value_semantics="average preparation duration",
        blocked_reason="production duration column/unit requires explicit verification",
    ),
    "picking": KpiDefinition(
        metric="picking",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="dmart_ops_picker_individual_performance_daily",
        value_semantics="picking duration per order",
        blocked_reason="production aggregation and duration-unit contract require explicit verification",
    ),
    "putaway": KpiDefinition(
        metric="putaway",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="dmart_ops_st_po_receiving_putaway_sku_details",
        value_semantics="putaway compliance / issue quantity according to reviewed inbound SLA",
        blocked_reason="ST/PO SLA and city-offset fields require explicit schema verification",
    ),
    "otp": KpiDefinition(
        metric="otp",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table="report__tableau_store_performance_report",
        value_semantics="OTP 4.25 = 100 - late_prep_rate_percent",
        blocked_reason="late-prep source column and percent scale require explicit verification",
    ),
    "defect": KpiDefinition(
        metric="defect",
        query_id=None,
        review_state="blocked_schema_verification",
        source_table=None,
        value_semantics="defect rate",
        blocked_reason="authoritative production defect denominator/source not yet pinned",
    ),
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
    return definition
