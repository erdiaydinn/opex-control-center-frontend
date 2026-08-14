from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Mapping

from .kpi_activation_gate import verify_duration_kpi_activation, verify_rate_kpi_activation
from .kpi_aggregation_contracts import WeightedAverageContract
from .kpi_rate_aggregation import RateAggregationContract
from .kpi_unit_contracts import DurationContract, RateContract


@dataclass(frozen=True)
class RuntimeProductionActivationArtifact:
    metric: str
    semantic_fingerprint: str
    schema_fingerprint: str
    schema_evidence_fingerprint: str
    source_semantics_fingerprint: str
    unit_contract_fingerprint: str
    aggregation_contract_fingerprint: str | None
    approval_reference: str
    reviewer: str
    reviewed_at: str
    approved_for_registry_review: bool = True
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"kpi_runtime_production_invalid_fingerprint:{field}")
    return text


def _review_gate(*, reviewer: str, reviewed_at: str, approval_reference: str) -> None:
    if not reviewer.strip():
        raise ValueError("kpi_runtime_production_reviewer_required")
    if not approval_reference.strip():
        raise ValueError("kpi_runtime_production_approval_reference_required")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("kpi_runtime_production_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("kpi_runtime_production_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("kpi_runtime_production_future_review_time")


def _require_common_lineage(
    *,
    metric: str,
    schema_verification: Mapping[str, object],
    source_semantics_verification: Mapping[str, object],
) -> tuple[str, str]:
    if source_semantics_verification.get("reviewed") is not True:
        raise ValueError("kpi_runtime_production_source_semantics_required")
    if source_semantics_verification.get("metric") != metric:
        raise ValueError("kpi_runtime_production_source_metric_mismatch")
    if schema_verification.get("verified") is not True:
        raise ValueError("kpi_runtime_production_schema_verification_required")

    evidence_fp = _sha(schema_verification.get("evidence_fingerprint"), "schema_evidence")
    mapped_evidence_fp = _sha(
        source_semantics_verification.get("schema_evidence_fingerprint"),
        "source_schema_evidence",
    )
    if evidence_fp != mapped_evidence_fp:
        raise ValueError("kpi_runtime_production_schema_lineage_mismatch")
    source_fp = _sha(
        source_semantics_verification.get("source_semantics_fingerprint"),
        "source_semantics",
    )
    return evidence_fp, source_fp


def seal_duration_production_activation(
    *,
    metric: str,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
    source_semantics_verification: Mapping[str, object],
    reviewer: str,
    reviewed_at: str,
    approval_reference: str,
) -> RuntimeProductionActivationArtifact:
    if metric not in {"prep", "picking"}:
        raise ValueError("kpi_runtime_production_not_duration_metric")
    _review_gate(
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        approval_reference=approval_reference,
    )
    evidence_fp, source_fp = _require_common_lineage(
        metric=metric,
        schema_verification=schema_verification,
        source_semantics_verification=source_semantics_verification,
    )

    unit = source_semantics_verification.get("unit_contract")
    aggregation = source_semantics_verification.get("aggregation_contract")
    if not isinstance(unit, DurationContract) or not isinstance(aggregation, WeightedAverageContract):
        raise ValueError("kpi_runtime_production_duration_contracts_required")
    if unit.metric != metric or aggregation.metric != metric:
        raise ValueError("kpi_runtime_production_duration_contract_metric_mismatch")

    bundle = verify_duration_kpi_activation(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
        unit_contract=unit,
        aggregation_contract=aggregation,
    )
    if bundle.schema_evidence_fingerprint != evidence_fp:
        raise ValueError("kpi_runtime_production_activation_schema_lineage_mismatch")

    return RuntimeProductionActivationArtifact(
        metric=metric,
        semantic_fingerprint=_sha(bundle.semantic_fingerprint, "semantic"),
        schema_fingerprint=_sha(bundle.schema_fingerprint, "schema"),
        schema_evidence_fingerprint=evidence_fp,
        source_semantics_fingerprint=source_fp,
        unit_contract_fingerprint=_sha(bundle.unit_contract_fingerprint, "unit_contract"),
        aggregation_contract_fingerprint=_sha(
            bundle.aggregation_contract_fingerprint, "aggregation_contract"
        ),
        approval_reference=approval_reference.strip(),
        reviewer=reviewer.strip(),
        reviewed_at=reviewed_at,
        approved_for_registry_review=True,
        executable=False,
    )


def seal_otp_production_activation(
    *,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
    source_semantics_verification: Mapping[str, object],
    reviewer: str,
    reviewed_at: str,
    approval_reference: str,
) -> RuntimeProductionActivationArtifact:
    metric = "otp"
    _review_gate(
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        approval_reference=approval_reference,
    )
    evidence_fp, source_fp = _require_common_lineage(
        metric=metric,
        schema_verification=schema_verification,
        source_semantics_verification=source_semantics_verification,
    )

    rate = source_semantics_verification.get("rate_contract")
    aggregation = source_semantics_verification.get("aggregation_contract")
    if not isinstance(rate, RateContract) or rate.metric != metric:
        raise ValueError("kpi_runtime_production_rate_contract_required")
    if not isinstance(aggregation, RateAggregationContract) or aggregation.metric != metric:
        raise ValueError("kpi_runtime_production_rate_aggregation_contract_required")

    late_prep_orders_column = str(
        source_semantics_verification.get("late_prep_orders_column") or ""
    ).strip().lower()
    eligible_orders_column = str(
        source_semantics_verification.get("eligible_orders_column") or ""
    ).strip().lower()
    if not late_prep_orders_column or not eligible_orders_column:
        raise ValueError("kpi_runtime_production_otp_lineage_columns_required")
    if late_prep_orders_column == eligible_orders_column:
        raise ValueError("kpi_runtime_production_otp_lineage_columns_must_differ")
    if (
        aggregation.numerator_field.strip().lower() != late_prep_orders_column
        or aggregation.denominator_field.strip().lower() != eligible_orders_column
    ):
        raise ValueError("kpi_runtime_production_otp_aggregation_lineage_mismatch")
    if aggregation.aggregation_kind != "complement_ratio_of_sums":
        raise ValueError("kpi_runtime_production_otp_aggregation_kind_mismatch")

    bundle = verify_rate_kpi_activation(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
        rate_contract=rate,
        aggregation_contract=aggregation,
    )
    if bundle.schema_evidence_fingerprint != evidence_fp:
        raise ValueError("kpi_runtime_production_activation_schema_lineage_mismatch")

    return RuntimeProductionActivationArtifact(
        metric=metric,
        semantic_fingerprint=_sha(bundle.semantic_fingerprint, "semantic"),
        schema_fingerprint=_sha(bundle.schema_fingerprint, "schema"),
        schema_evidence_fingerprint=evidence_fp,
        source_semantics_fingerprint=source_fp,
        unit_contract_fingerprint=_sha(bundle.unit_contract_fingerprint, "rate_contract"),
        aggregation_contract_fingerprint=_sha(
            bundle.aggregation_contract_fingerprint, "aggregation_contract"
        ),
        approval_reference=approval_reference.strip(),
        reviewer=reviewer.strip(),
        reviewed_at=reviewed_at,
        approved_for_registry_review=True,
        executable=False,
    )
