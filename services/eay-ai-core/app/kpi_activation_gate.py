from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .kpi_aggregation_contracts import WeightedAverageContract, validate_weighted_average_contract
from .kpi_unit_contracts import DurationContract, RateContract


@dataclass(frozen=True)
class KpiActivationBundle:
    metric: str
    semantic_fingerprint: str
    schema_fingerprint: str
    schema_evidence_fingerprint: str | None
    unit_contract_fingerprint: str
    aggregation_contract_fingerprint: str


@dataclass(frozen=True)
class KpiRateActivationBundle:
    metric: str
    semantic_fingerprint: str
    schema_fingerprint: str
    schema_evidence_fingerprint: str | None
    unit_contract_fingerprint: str
    aggregation_contract_fingerprint: None = None


def _sha256_fingerprint(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"kpi_activation_invalid_fingerprint:{field}")
    return text


def _verified_lineage(
    *,
    metric: str,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
) -> tuple[str, str, str | None]:
    if not metric.strip():
        raise ValueError("kpi_activation_metric_required")
    if semantic_verification.get("metric") != metric or semantic_verification.get("reviewed") is not True:
        raise ValueError("kpi_activation_semantic_verification_required")
    if schema_verification.get("verified") is not True:
        raise ValueError("kpi_activation_schema_verification_required")

    semantic_fp = _sha256_fingerprint(
        semantic_verification.get("fingerprint"), "semantic"
    )
    schema_fp = _sha256_fingerprint(
        schema_verification.get("observed_fingerprint"), "schema"
    )
    evidence_raw = schema_verification.get("evidence_fingerprint")
    evidence_fp = (
        _sha256_fingerprint(evidence_raw, "schema_evidence")
        if evidence_raw is not None
        else None
    )
    return semantic_fp, schema_fp, evidence_fp


def verify_duration_kpi_activation(
    *,
    metric: str,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
    unit_contract: DurationContract,
    aggregation_contract: WeightedAverageContract,
) -> KpiActivationBundle:
    """Require semantic, schema, unit and aggregation contracts to agree before activation."""

    semantic_fp, schema_fp, evidence_fp = _verified_lineage(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
    )
    if unit_contract.metric != metric:
        raise ValueError("kpi_activation_unit_metric_mismatch")
    if aggregation_contract.metric != metric:
        raise ValueError("kpi_activation_aggregation_metric_mismatch")

    validate_weighted_average_contract(aggregation_contract)
    if unit_contract.output_unit != aggregation_contract.output_unit:
        raise ValueError("kpi_activation_output_unit_mismatch")

    return KpiActivationBundle(
        metric=metric,
        semantic_fingerprint=semantic_fp,
        schema_fingerprint=schema_fp,
        schema_evidence_fingerprint=evidence_fp,
        unit_contract_fingerprint=unit_contract.fingerprint,
        aggregation_contract_fingerprint=aggregation_contract.fingerprint,
    )


def verify_rate_kpi_activation(
    *,
    metric: str,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
    rate_contract: RateContract,
) -> KpiRateActivationBundle:
    """Require an explicitly pinned source scale for percentage KPIs such as OTP."""

    semantic_fp, schema_fp, evidence_fp = _verified_lineage(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
    )
    if rate_contract.metric != metric:
        raise ValueError("kpi_activation_unit_metric_mismatch")

    return KpiRateActivationBundle(
        metric=metric,
        semantic_fingerprint=semantic_fp,
        schema_fingerprint=schema_fp,
        schema_evidence_fingerprint=evidence_fp,
        unit_contract_fingerprint=rate_contract.fingerprint,
    )
