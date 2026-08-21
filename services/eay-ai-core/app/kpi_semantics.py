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
        review_state="reviewed",
        numerator="orders classified as PFR, else Refund, else Compensation",
        denominator="successful_orders",
        unit="rate_percent",
        aggregation="precedence-aware mutually exclusive order classification / successful_orders",
        precedence=("PFR overrides Refund", "Refund overrides Compensation"),
        notes=(
            "Semantic review is independent from production schema activation. "
            "Execution remains blocked until a live schema contract is pinned and verified. "
            "Product-failure updates may be excluded only by an explicitly reviewed query variant."
        ),
    ),
    "ops.pfr.semantic.v1": KpiSemanticContract(
        contract_id="ops.pfr.semantic.v1",
        metric="pfr",
        review_state="reviewed",
        numerator="pfr_orders",
        denominator="successful_orders",
        unit="rate_percent",
        aggregation="pfr_orders / successful_orders",
        precedence=("PFR has first precedence within NSFR decomposition",),
        notes="Execution remains blocked until the production schema contract is pinned and verified.",
    ),
    "ops.refund.semantic.v1": KpiSemanticContract(
        contract_id="ops.refund.semantic.v1",
        metric="refund",
        review_state="reviewed",
        numerator="refund_orders after PFR precedence",
        denominator="successful_orders",
        unit="rate_percent",
        aggregation="precedence-adjusted refund_orders / successful_orders",
        precedence=("PFR overrides Refund", "Refund overrides Compensation"),
        notes="Execution remains blocked until the production schema contract is pinned and verified.",
    ),
    "ops.prep.semantic.v1": KpiSemanticContract(
        contract_id="ops.prep.semantic.v1",
        metric="prep",
        review_state="blocked_pending_schema",
        numerator="sum of reviewed preparation duration",
        denominator="eligible orders with valid preparation duration",
        unit="seconds_per_order",
        aggregation="weighted average duration per eligible order",
        notes=(
            "Production source duration unit must be explicitly pinned as seconds or minutes; "
            "value-based unit guessing is forbidden before activation."
        ),
    ),
    "ops.picking.semantic.v1": KpiSemanticContract(
        contract_id="ops.picking.semantic.v1",
        metric="picking",
        review_state="blocked_pending_schema",
        numerator="sum of reviewed picking duration",
        denominator="eligible picked orders",
        unit="seconds_per_order",
        aggregation="weighted average picking duration per order",
        notes=(
            "Production source duration unit and aggregation grain must be explicitly reviewed; "
            "the runtime normalizes only from a pinned seconds/minutes contract."
        ),
    ),
    "ops.otp.semantic.v1": KpiSemanticContract(
        contract_id="ops.otp.semantic.v1",
        metric="otp",
        review_state="blocked_pending_schema",
        numerator="100 - late_prep_rate_percent",
        denominator="100 percent scale",
        unit="percent",
        aggregation="OTP 4.25 percentage from reviewed late-prep percentage",
        notes=(
            "late_prep_rate source scale must be explicitly pinned as fraction or percent. "
            "Heuristics such as value <= 1 => fraction are forbidden because values like 0.8 are ambiguous."
        ),
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
