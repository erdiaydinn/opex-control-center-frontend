from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

SemanticReviewState = Literal["reviewed", "blocked_pending_schema"]


@dataclass(frozen=True)
class KpiSemanticContract:
    contract_id: str
    metric: str
    review_state: SemanticReviewState
    numerator: str
    denominator: str
    unit: str
    aggregation: str
    precedence: tuple[str, ...] = ()
    notes: str | None = None

    @property
    def fingerprint(self) -> str:
        payload = {
            "contract_id": self.contract_id,
            "metric": self.metric,
            "review_state": self.review_state,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "unit": self.unit,
            "aggregation": self.aggregation,
            "precedence": list(self.precedence),
            "notes": self.notes,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


SEMANTIC_CONTRACTS: dict[str, KpiSemanticContract] = {
    "ops.orders.semantic.v1": KpiSemanticContract(
        contract_id="ops.orders.semantic.v1",
        metric="orders",
        review_state="reviewed",
        numerator="distinct order_id",
        denominator="none",
        unit="count",
        aggregation="COUNT(DISTINCT order_id) by local date and store",
    ),
    "ops.nsfr.semantic.v1": KpiSemanticContract(
        contract_id="ops.nsfr.semantic.v1",
        metric="nsfr",
        review_state="blocked_pending_schema",
        numerator="orders classified as PFR, else Refund, else Compensation",
        denominator="eligible completed market orders",
        unit="rate_percent",
        aggregation="precedence-aware mutually exclusive order classification / eligible orders",
        precedence=("PFR overrides Refund", "Refund overrides Compensation"),
        notes="Product-failure updates may be excluded only when an explicitly reviewed query contract requests that variant.",
    ),
    "ops.pfr.semantic.v1": KpiSemanticContract(
        contract_id="ops.pfr.semantic.v1",
        metric="pfr",
        review_state="blocked_pending_schema",
        numerator="orders classified as partially fulfilled",
        denominator="eligible completed market orders",
        unit="rate_percent",
        aggregation="distinct affected orders / eligible orders",
        precedence=("PFR has first precedence within NSFR decomposition",),
    ),
    "ops.refund.semantic.v1": KpiSemanticContract(
        contract_id="ops.refund.semantic.v1",
        metric="refund",
        review_state="blocked_pending_schema",
        numerator="refunded orders not already classified as PFR",
        denominator="eligible completed market orders",
        unit="rate_percent",
        aggregation="distinct precedence-adjusted refund orders / eligible orders",
        precedence=("PFR overrides Refund", "Refund overrides Compensation"),
    ),
    "ops.prep.semantic.v1": KpiSemanticContract(
        contract_id="ops.prep.semantic.v1",
        metric="prep",
        review_state="blocked_pending_schema",
        numerator="sum of reviewed preparation duration",
        denominator="eligible orders with valid preparation duration",
        unit="seconds_per_order",
        aggregation="weighted average duration per eligible order",
    ),
    "ops.picking.semantic.v1": KpiSemanticContract(
        contract_id="ops.picking.semantic.v1",
        metric="picking",
        review_state="blocked_pending_schema",
        numerator="sum of reviewed picking duration",
        denominator="eligible picked orders",
        unit="seconds_per_order",
        aggregation="weighted average picking duration per order",
    ),
    "ops.otp.semantic.v1": KpiSemanticContract(
        contract_id="ops.otp.semantic.v1",
        metric="otp",
        review_state="blocked_pending_schema",
        numerator="100 - late_prep_rate_percent",
        denominator="100 percent scale",
        unit="percent",
        aggregation="OTP 4.25 percentage from reviewed late-prep percentage",
    ),
    "ops.putaway.semantic.v1": KpiSemanticContract(
        contract_id="ops.putaway.semantic.v1",
        metric="putaway",
        review_state="blocked_pending_schema",
        numerator="putaway-compliant inbound quantity or records",
        denominator="eligible inbound quantity or records under reviewed SLA",
        unit="rate_percent",
        aggregation="SLA-aware compliance rate; ST cDC 240m, ST other 960m plus reviewed offsets, PO 240m",
    ),
}


def get_semantic_contract(contract_id: str) -> KpiSemanticContract:
    contract = SEMANTIC_CONTRACTS.get(contract_id)
    if contract is None:
        raise ValueError(f"unknown_kpi_semantic_contract:{contract_id}")
    return contract


def verify_semantic_contract(*, metric: str, contract_id: str) -> dict[str, object]:
    contract = get_semantic_contract(contract_id)
    if contract.metric != metric:
        raise ValueError(f"kpi_semantic_contract_metric_mismatch:{metric}:{contract_id}")
    if contract.review_state != "reviewed":
        raise ValueError(f"kpi_semantic_contract_not_reviewed:{metric}:{contract_id}")
    return {
        "contract_id": contract.contract_id,
        "metric": contract.metric,
        "fingerprint": contract.fingerprint,
        "reviewed": True,
    }
