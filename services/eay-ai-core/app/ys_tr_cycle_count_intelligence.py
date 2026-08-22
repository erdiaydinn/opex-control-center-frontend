"""Reviewed Yemeksepeti TR cycle-count business semantics for Jarvis.

This module is repository/company knowledge, not live production evidence.  It
captures the reviewed business rule supplied by the operator so Jarvis can
reason consistently about weekly cycle-count compliance while keeping live
BigQuery execution behind the existing governed source/tenant gates.

Key rule:
- reporting week is Monday through Sunday;
- a cycle belongs permanently to the week of ``cycle_count_created_at_date``;
- successful weekly completion requires completion no later than the Sunday of
  that same assignment week;
- a cycle completed in a later week is late and never gives credit to the later
  week;
- the main monthly compliance score is completed required weeks / required
  weeks, expressed on a 0..1 scale;
- for HYBRID after 2026-04-13 the nominal weekly SKU target is 210, but SKU
  target attainment is a secondary metric and must not replace weekly
  compliance.

The source schema/column names below are user-reviewed company knowledge.  They
do not by themselves prove production schema types or grant execution/truth
authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date

YS_TR_CYCLE_COUNT_KNOWLEDGE_CONTRACT = "ys-tr-cycle-count-weekly-compliance-v1"
YS_TR_CYCLE_COUNT_SOURCE_TABLE = (
    "fulfillment-dwh-production.curated_data_shared_dmart.cycle_count_details"
)
YS_TR_CYCLE_COUNT_TENANT = "YS_TR"
YS_TR_HYBRID_GO_LIVE_DATE = date(2026, 4, 13)
YS_TR_HYBRID_WEEKLY_SKU_TARGET = 210


@dataclass(frozen=True)
class YsTrCycleCountRule:
    contract_id: str
    tenant_id: str
    source_table: str
    assignment_date_field: str
    completion_date_field: str
    status_field: str
    strategy_field: str
    cycle_id_field: str
    sku_field: str
    week_start: str
    week_end: str
    completion_deadline: str
    assignment_ownership_rule: str
    late_completion_rule: str
    main_metric: str
    main_metric_scale: str
    hybrid_go_live_date: date
    hybrid_weekly_sku_target: int

    @property
    def fingerprint(self) -> str:
        payload = {
            "contract_id": self.contract_id,
            "tenant_id": self.tenant_id,
            "source_table": self.source_table,
            "assignment_date_field": self.assignment_date_field,
            "completion_date_field": self.completion_date_field,
            "status_field": self.status_field,
            "strategy_field": self.strategy_field,
            "cycle_id_field": self.cycle_id_field,
            "sku_field": self.sku_field,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "completion_deadline": self.completion_deadline,
            "assignment_ownership_rule": self.assignment_ownership_rule,
            "late_completion_rule": self.late_completion_rule,
            "main_metric": self.main_metric,
            "main_metric_scale": self.main_metric_scale,
            "hybrid_go_live_date": self.hybrid_go_live_date.isoformat(),
            "hybrid_weekly_sku_target": self.hybrid_weekly_sku_target,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


RULE = YsTrCycleCountRule(
    contract_id=YS_TR_CYCLE_COUNT_KNOWLEDGE_CONTRACT,
    tenant_id=YS_TR_CYCLE_COUNT_TENANT,
    source_table=YS_TR_CYCLE_COUNT_SOURCE_TABLE,
    assignment_date_field="cycle_count_created_at_date",
    completion_date_field="cycle_count_completed_at_date",
    status_field="cycle_count_status",
    strategy_field="strategy",
    cycle_id_field="cycle_count_id",
    sku_field="sku",
    week_start="MONDAY",
    week_end="SUNDAY",
    completion_deadline="SUNDAY",
    assignment_ownership_rule=(
        "A cycle belongs only to the Monday-Sunday week containing "
        "cycle_count_created_at_date."
    ),
    late_completion_rule=(
        "Completion after that week's Sunday is late; it does not complete the "
        "assignment week and cannot give credit to the later week."
    ),
    main_metric="total_completion_rate",
    main_metric_scale="0_to_1",
    hybrid_go_live_date=YS_TR_HYBRID_GO_LIVE_DATE,
    hybrid_weekly_sku_target=YS_TR_HYBRID_WEEKLY_SKU_TARGET,
)


def cycle_count_company_knowledge_text() -> str:
    """Return concise retrievable company knowledge for grounded Jarvis answers."""

    return (
        "Yemeksepeti TR (YS_TR) cycle count weekly compliance rule. "
        "Source: fulfillment-dwh-production.curated_data_shared_dmart."
        "cycle_count_details. Assignment is cycle_count_created_at_date and "
        "completion is cycle_count_completed_at_date. Reporting week is Monday "
        "through Sunday. A cycle is owned permanently by the week in which it "
        "was created/assigned. To receive weekly completion credit it must be "
        "COMPLETE/COMPLETED no later than Sunday of that same week. If a cycle "
        "assigned in one week is completed in the following Monday or later, it "
        "is late: it does not complete the original week and it must not give "
        "credit to the later week. Main monthly KPI is total_completion_rate = "
        "completed required weeks / required weeks on a 0..1 scale (for four "
        "required weeks: 0, 0.25, 0.50, 0.75, 1.00). After 2026-04-13 HYBRID is "
        "the weekly operating strategy with nominal 210 SKU/week; SKU target "
        "attainment is secondary and must not replace weekly compliance."
    )


def is_cycle_count_question(message: str) -> bool:
    text = " ".join(str(message or "").casefold().replace("ı", "i").split())
    markers = (
        "cycle count",
        "cycle_count",
        "sayim",
        "sayım",
        "hybrid",
        "total_completion_rate",
        "cycle_count_created_at_date",
        "cycle_count_completed_at_date",
    )
    return any(marker.casefold().replace("ı", "i") in text for marker in markers)


def explain_cycle_count_rule(message: str) -> str | None:
    """Deterministic fallback explanation for reviewed YS_TR cycle-count questions."""

    if not is_cycle_count_question(message):
        return None
    return cycle_count_company_knowledge_text()
