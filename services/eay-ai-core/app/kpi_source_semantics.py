from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Mapping

from .kpi_aggregation_contracts import WeightedAverageContract
from .kpi_rate_aggregation import RateAggregationContract
from .kpi_schema_evidence import KpiSchemaEvidence
from .kpi_unit_contracts import DurationContract, RateContract

SourceGrain = Literal["order", "picker_day", "event"]
DurationMetric = Literal["prep", "picking"]
RateMetric = Literal["otp"]

_NUMERIC_TYPES = {
    "INT64",
    "INTEGER",
    "NUMERIC",
    "BIGNUMERIC",
    "FLOAT64",
    "FLOAT",
    "DECIMAL",
    "BIGDECIMAL",
}
_DATE_TYPES = {"DATE", "DATETIME", "TIMESTAMP"}
_EXPECTED_TABLES = {
    "prep": "report__tableau_store_performance_report",
    "picking": "dmart_ops_picker_individual_performance_daily",
    "otp": "report__tableau_store_performance_report",
}


@dataclass(frozen=True)
class DurationSourceSemantics:
    metric: DurationMetric
    table_id: str
    role_to_column: Mapping[str, str]
    schema_evidence_fingerprint: str
    source_grain: SourceGrain
    source_unit: Literal["seconds", "minutes"]
    reviewed_at: str
    reviewer: str | None = None
    reviewed: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "kind": "duration_source_semantics",
            "metric": self.metric,
            "table_id": self.table_id,
            "role_to_column": _canonical_mapping(self.role_to_column),
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "source_grain": self.source_grain,
            "source_unit": self.source_unit,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "reviewed": self.reviewed,
        }
        return _fingerprint(payload)


@dataclass(frozen=True)
class RateSourceSemantics:
    metric: RateMetric
    table_id: str
    role_to_column: Mapping[str, str]
    schema_evidence_fingerprint: str
    source_scale: Literal["fraction", "percent"]
    reviewed_at: str
    reviewer: str | None = None
    reviewed: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "kind": "rate_source_semantics",
            "metric": self.metric,
            "table_id": self.table_id,
            "role_to_column": _canonical_mapping(self.role_to_column),
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "source_scale": self.source_scale,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "reviewed": self.reviewed,
        }
        return _fingerprint(payload)


def _fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_mapping(mapping: Mapping[str, str]) -> dict[str, str]:
    return {
        str(role).strip().lower(): str(column).strip().lower()
        for role, column in sorted(mapping.items())
    }


def _reviewed_evidence(evidence: KpiSchemaEvidence, *, metric: str, fingerprint: str) -> dict[str, str]:
    expected_table = _EXPECTED_TABLES[metric]
    if evidence.table_id != expected_table:
        raise ValueError("kpi_source_semantics_table_mismatch")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("kpi_source_semantics_reviewed_schema_evidence_required")
    if fingerprint != evidence.fingerprint:
        raise ValueError("kpi_source_semantics_schema_evidence_mismatch")
    return evidence.canonical_columns


def _validate_review(reviewed_at: str, reviewer: str | None, reviewed: bool) -> None:
    if not reviewed or not (reviewer or "").strip():
        raise ValueError("kpi_source_semantics_human_review_required")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("kpi_source_semantics_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("kpi_source_semantics_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("kpi_source_semantics_future_review_time")


def _require_column(
    *,
    mapping: Mapping[str, str],
    observed: Mapping[str, str],
    role: str,
    allowed_types: set[str],
) -> str:
    column = mapping.get(role, "")
    if not column:
        raise ValueError(f"kpi_source_semantics_missing_role:{role}")
    if column not in observed:
        raise ValueError(f"kpi_source_semantics_unobserved_column:{role}:{column}")
    field_type = observed[column]
    if field_type not in allowed_types:
        raise ValueError(f"kpi_source_semantics_invalid_type:{role}:{field_type}")
    return column


def verify_duration_source_semantics(
    evidence: KpiSchemaEvidence,
    semantics: DurationSourceSemantics,
) -> dict[str, object]:
    """Bind duration unit + aggregation grain to reviewed production columns.

    No value-based unit inference is permitted. Picker-day sources additionally require
    an explicit eligible-order weight, preventing an average-of-averages activation.
    """

    _validate_review(semantics.reviewed_at, semantics.reviewer, semantics.reviewed)
    observed = _reviewed_evidence(
        evidence,
        metric=semantics.metric,
        fingerprint=semantics.schema_evidence_fingerprint,
    )
    if semantics.table_id != _EXPECTED_TABLES[semantics.metric]:
        raise ValueError("kpi_source_semantics_table_mismatch")
    mapping = _canonical_mapping(semantics.role_to_column)
    duration_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="duration_value",
        allowed_types=_NUMERIC_TYPES,
    )
    date_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="date",
        allowed_types=_DATE_TYPES,
    )
    store_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="store",
        allowed_types={"STRING"},
    )

    weight_column: str | None = None
    if semantics.source_grain == "picker_day":
        weight_column = _require_column(
            mapping=mapping,
            observed=observed,
            role="eligible_orders",
            allowed_types=_NUMERIC_TYPES,
        )

    unit = DurationContract(metric=semantics.metric, source_unit=semantics.source_unit)
    aggregation = WeightedAverageContract(
        metric=semantics.metric,
        source_grain=semantics.source_grain,
        value_field=duration_column,
        weight_field=weight_column,
        output_unit=unit.output_unit,
    )
    return {
        "metric": semantics.metric,
        "table_id": semantics.table_id,
        "duration_column": duration_column,
        "date_column": date_column,
        "store_column": store_column,
        "weight_column": weight_column,
        "source_grain": semantics.source_grain,
        "source_unit": semantics.source_unit,
        "schema_evidence_fingerprint": evidence.fingerprint,
        "source_semantics_fingerprint": semantics.fingerprint,
        "unit_contract": unit,
        "aggregation_contract": aggregation,
        "reviewed": True,
    }


def verify_otp_source_semantics(
    evidence: KpiSchemaEvidence,
    semantics: RateSourceSemantics,
) -> dict[str, object]:
    """Bind OTP 4.25 to reviewed additive late/eligible-order lineage.

    A pre-aggregated late-prep percentage may still be mapped for row-level display or
    reconciliation, but it is never sufficient for aggregate OTP activation. Production
    aggregation must use SUM(late_prep_orders) / SUM(eligible_orders), then complement
    the ratio to OTP. This prevents average-of-percentages drift when store/day group
    sizes differ.
    """

    if semantics.metric != "otp":
        raise ValueError("kpi_source_semantics_metric_mismatch")
    _validate_review(semantics.reviewed_at, semantics.reviewer, semantics.reviewed)
    observed = _reviewed_evidence(
        evidence,
        metric="otp",
        fingerprint=semantics.schema_evidence_fingerprint,
    )
    if semantics.table_id != _EXPECTED_TABLES["otp"]:
        raise ValueError("kpi_source_semantics_table_mismatch")
    mapping = _canonical_mapping(semantics.role_to_column)
    date_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="date",
        allowed_types=_DATE_TYPES,
    )
    store_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="store",
        allowed_types={"STRING"},
    )
    late_prep_orders_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="late_prep_orders",
        allowed_types=_NUMERIC_TYPES,
    )
    eligible_orders_column = _require_column(
        mapping=mapping,
        observed=observed,
        role="eligible_orders",
        allowed_types=_NUMERIC_TYPES,
    )
    if late_prep_orders_column == eligible_orders_column:
        raise ValueError("kpi_source_semantics_otp_numerator_denominator_must_differ")

    late_prep_rate_column: str | None = None
    if mapping.get("late_prep_rate"):
        late_prep_rate_column = _require_column(
            mapping=mapping,
            observed=observed,
            role="late_prep_rate",
            allowed_types=_NUMERIC_TYPES,
        )
        if late_prep_rate_column in {late_prep_orders_column, eligible_orders_column}:
            raise ValueError("kpi_source_semantics_otp_rate_column_must_be_distinct")

    rate = RateContract(metric="otp", source_scale=semantics.source_scale)
    aggregation = RateAggregationContract(
        metric="otp",
        numerator_field=late_prep_orders_column,
        denominator_field=eligible_orders_column,
        aggregation_kind="complement_ratio_of_sums",
    )
    return {
        "metric": "otp",
        "table_id": semantics.table_id,
        "late_prep_rate_column": late_prep_rate_column,
        "late_prep_orders_column": late_prep_orders_column,
        "eligible_orders_column": eligible_orders_column,
        "date_column": date_column,
        "store_column": store_column,
        "source_scale": semantics.source_scale,
        "schema_evidence_fingerprint": evidence.fingerprint,
        "source_semantics_fingerprint": semantics.fingerprint,
        "rate_contract": rate,
        "aggregation_contract": aggregation,
        "reviewed": True,
    }
