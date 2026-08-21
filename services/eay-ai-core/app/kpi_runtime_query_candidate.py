from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping

from .kpi_aggregation_contracts import WeightedAverageContract
from .kpi_rate_aggregation import RateAggregationContract
from .kpi_unit_contracts import DurationContract, RateContract

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){0,2}$")


@dataclass(frozen=True)
class RuntimeKpiQueryCandidate:
    candidate_id: str
    metric: str
    table_id: str
    sql: str
    parameter_names: tuple[str, ...]
    schema_evidence_fingerprint: str
    source_semantics_fingerprint: str
    unit_contract_fingerprint: str
    aggregation_contract_fingerprint: str
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "candidate_id": self.candidate_id,
            "metric": self.metric,
            "table_id": self.table_id,
            "sql": self.sql,
            "parameter_names": list(self.parameter_names),
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "source_semantics_fingerprint": self.source_semantics_fingerprint,
            "unit_contract_fingerprint": self.unit_contract_fingerprint,
            "aggregation_contract_fingerprint": self.aggregation_contract_fingerprint,
            "executable": self.executable,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"runtime_query_candidate_invalid_fingerprint:{field}")
    return text


def _identifier(value: object, field: str) -> str:
    text = str(value or "")
    if not _IDENTIFIER_RE.fullmatch(text):
        raise ValueError(f"runtime_query_candidate_invalid_identifier:{field}")
    return text


def _base(candidate_id: str, verified_source: Mapping[str, object]) -> tuple[str, str, str, str]:
    if not candidate_id.strip():
        raise ValueError("runtime_query_candidate_id_required")
    if verified_source.get("reviewed") is not True:
        raise ValueError("runtime_query_candidate_reviewed_source_required")
    metric = str(verified_source.get("metric") or "")
    if metric not in {"prep", "picking", "otp"}:
        raise ValueError("runtime_query_candidate_metric_unsupported")
    table_id = str(verified_source.get("table_id") or "")
    if not _TABLE_RE.fullmatch(table_id):
        raise ValueError("runtime_query_candidate_invalid_table")
    evidence_fp = _sha(verified_source.get("schema_evidence_fingerprint"), "schema_evidence")
    semantics_fp = _sha(verified_source.get("source_semantics_fingerprint"), "source_semantics")
    return metric, table_id, evidence_fp, semantics_fp


def build_duration_query_candidate(*, candidate_id: str, verified_source: Mapping[str, object]) -> RuntimeKpiQueryCandidate:
    metric, table_id, evidence_fp, semantics_fp = _base(candidate_id, verified_source)
    if metric not in {"prep", "picking"}:
        raise ValueError("runtime_query_candidate_duration_metric_required")
    date_column = _identifier(verified_source.get("date_column"), "date")
    store_column = _identifier(verified_source.get("store_column"), "store")
    duration_column = _identifier(verified_source.get("duration_column"), "duration")
    source_unit = str(verified_source.get("source_unit") or "")
    source_grain = str(verified_source.get("source_grain") or "")
    unit_contract = verified_source.get("unit_contract")
    aggregation_contract = verified_source.get("aggregation_contract")
    if not isinstance(unit_contract, DurationContract) or unit_contract.metric != metric or unit_contract.source_unit != source_unit:
        raise ValueError("runtime_query_candidate_unit_contract_mismatch")
    if not isinstance(aggregation_contract, WeightedAverageContract) or aggregation_contract.metric != metric:
        raise ValueError("runtime_query_candidate_aggregation_contract_mismatch")
    if aggregation_contract.value_field != duration_column or aggregation_contract.source_grain != source_grain:
        raise ValueError("runtime_query_candidate_aggregation_lineage_mismatch")

    value_expr = f"CAST(`{duration_column}` AS NUMERIC)"
    if source_unit == "minutes":
        value_expr = f"({value_expr} * 60)"
    elif source_unit != "seconds":
        raise ValueError("runtime_query_candidate_duration_unit_unsupported")

    if source_grain == "picker_day":
        weight_column = _identifier(verified_source.get("weight_column"), "eligible_orders")
        if aggregation_contract.weight_field != weight_column:
            raise ValueError("runtime_query_candidate_weight_lineage_mismatch")
        metric_expr = (
            f"SAFE_DIVIDE(SUM({value_expr} * CAST(`{weight_column}` AS NUMERIC)), "
            f"SUM(CAST(`{weight_column}` AS NUMERIC)))"
        )
    elif source_grain in {"order", "event"}:
        if aggregation_contract.weight_field is not None:
            raise ValueError("runtime_query_candidate_unexpected_weight")
        metric_expr = f"AVG({value_expr})"
    else:
        raise ValueError("runtime_query_candidate_source_grain_unsupported")

    sql = (
        f"SELECT\n  DATE(`{date_column}`) AS date,\n  `{store_column}` AS store,\n"
        f"  {metric_expr} AS {metric}_seconds_per_order\n"
        f"FROM `{table_id}`\n"
        f"WHERE DATE(`{date_column}`) BETWEEN @start_date AND @end_date\n"
        f"  AND (@stores_empty OR `{store_column}` IN UNNEST(@stores))\n"
        "GROUP BY 1,2\nORDER BY 1 DESC,2 ASC"
    )
    return RuntimeKpiQueryCandidate(
        candidate_id=candidate_id,
        metric=metric,
        table_id=table_id,
        sql=sql,
        parameter_names=("start_date", "end_date", "stores", "stores_empty"),
        schema_evidence_fingerprint=evidence_fp,
        source_semantics_fingerprint=semantics_fp,
        unit_contract_fingerprint=unit_contract.fingerprint,
        aggregation_contract_fingerprint=aggregation_contract.fingerprint,
        executable=False,
    )


def build_otp_query_candidate(*, candidate_id: str, verified_source: Mapping[str, object]) -> RuntimeKpiQueryCandidate:
    metric, table_id, evidence_fp, semantics_fp = _base(candidate_id, verified_source)
    if metric != "otp":
        raise ValueError("runtime_query_candidate_otp_metric_required")
    date_column = _identifier(verified_source.get("date_column"), "date")
    store_column = _identifier(verified_source.get("store_column"), "store")
    numerator = _identifier(verified_source.get("late_prep_orders_column"), "late_prep_orders")
    denominator = _identifier(verified_source.get("eligible_orders_column"), "eligible_orders")
    if numerator == denominator:
        raise ValueError("runtime_query_candidate_otp_numerator_denominator_must_differ")
    rate_contract = verified_source.get("rate_contract")
    aggregation_contract = verified_source.get("aggregation_contract")
    if not isinstance(rate_contract, RateContract) or rate_contract.metric != "otp":
        raise ValueError("runtime_query_candidate_rate_contract_mismatch")
    if not isinstance(aggregation_contract, RateAggregationContract):
        raise ValueError("runtime_query_candidate_aggregation_contract_mismatch")
    if aggregation_contract.metric != "otp" or aggregation_contract.aggregation_kind != "complement_ratio_of_sums":
        raise ValueError("runtime_query_candidate_otp_aggregation_kind_required")
    if aggregation_contract.numerator_field != numerator or aggregation_contract.denominator_field != denominator:
        raise ValueError("runtime_query_candidate_otp_aggregation_lineage_mismatch")

    sql = (
        f"SELECT\n  DATE(`{date_column}`) AS date,\n  `{store_column}` AS store,\n"
        f"  100 - (SAFE_DIVIDE(SUM(CAST(`{numerator}` AS NUMERIC)), "
        f"SUM(CAST(`{denominator}` AS NUMERIC))) * 100) AS otp_4_25_percent\n"
        f"FROM `{table_id}`\n"
        f"WHERE DATE(`{date_column}`) BETWEEN @start_date AND @end_date\n"
        f"  AND (@stores_empty OR `{store_column}` IN UNNEST(@stores))\n"
        "GROUP BY 1,2\nORDER BY 1 DESC,2 ASC"
    )
    return RuntimeKpiQueryCandidate(
        candidate_id=candidate_id,
        metric="otp",
        table_id=table_id,
        sql=sql,
        parameter_names=("start_date", "end_date", "stores", "stores_empty"),
        schema_evidence_fingerprint=evidence_fp,
        source_semantics_fingerprint=semantics_fp,
        unit_contract_fingerprint=rate_contract.fingerprint,
        aggregation_contract_fingerprint=aggregation_contract.fingerprint,
        executable=False,
    )
