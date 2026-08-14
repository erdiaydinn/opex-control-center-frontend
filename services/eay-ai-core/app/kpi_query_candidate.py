from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){0,2}$")
_NSFR_ROLES = (
    "eligible_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)
_NUMERIC_TYPES = {"INT64", "INTEGER", "NUMERIC", "BIGNUMERIC", "FLOAT64", "FLOAT", "DECIMAL", "BIGDECIMAL"}
_DATE_TYPES = {"DATE", "DATETIME", "TIMESTAMP"}


@dataclass(frozen=True)
class KpiQueryTemplateCandidate:
    candidate_id: str
    metric_family: str
    table_id: str
    sql: str
    parameter_names: tuple[str, ...]
    schema_manifest_fingerprint: str
    schema_approval_fingerprint: str
    semantic_mapping_fingerprint: str
    dimension_mapping_fingerprint: str | None = None
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "candidate_id": self.candidate_id,
            "metric_family": self.metric_family,
            "table_id": self.table_id,
            "sql": self.sql,
            "parameter_names": list(self.parameter_names),
            "schema_manifest_fingerprint": self.schema_manifest_fingerprint,
            "schema_approval_fingerprint": self.schema_approval_fingerprint,
            "semantic_mapping_fingerprint": self.semantic_mapping_fingerprint,
            "dimension_mapping_fingerprint": self.dimension_mapping_fingerprint,
            "executable": self.executable,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"kpi_query_candidate_invalid_fingerprint:{field}")
    return text


def _base_inputs(
    *,
    candidate_id: str,
    manifest_approval: Mapping[str, object],
    semantic_mapping: Mapping[str, object],
) -> tuple[str, str, Mapping[str, object], Mapping[str, object]]:
    if not candidate_id.strip():
        raise ValueError("kpi_query_candidate_id_required")
    if manifest_approval.get("verified") is not True:
        raise ValueError("kpi_query_candidate_schema_approval_required")
    if semantic_mapping.get("verified") is not True:
        raise ValueError("kpi_query_candidate_semantic_mapping_required")
    if semantic_mapping.get("metric_family") != "nsfr_family":
        raise ValueError("kpi_query_candidate_metric_family_mismatch")

    table_id = str(manifest_approval.get("table_id") or "")
    if table_id != str(semantic_mapping.get("table_id") or ""):
        raise ValueError("kpi_query_candidate_table_mismatch")
    if not _TABLE_RE.fullmatch(table_id):
        raise ValueError("kpi_query_candidate_invalid_table_identifier")

    evidence_fp = _sha(manifest_approval.get("evidence_fingerprint"), "evidence")
    if evidence_fp != _sha(semantic_mapping.get("schema_evidence_fingerprint"), "mapping_evidence"):
        raise ValueError("kpi_query_candidate_schema_evidence_mismatch")

    role_map = semantic_mapping.get("role_to_column")
    role_types = semantic_mapping.get("role_types")
    if not isinstance(role_map, Mapping) or not isinstance(role_types, Mapping):
        raise ValueError("kpi_query_candidate_role_mapping_required")
    return table_id, evidence_fp, role_map, role_types


def _measure_projection(
    role_map: Mapping[str, object],
    role_types: Mapping[str, object],
) -> list[str]:
    selected: list[str] = []
    for role in _NSFR_ROLES:
        column = str(role_map.get(role) or "")
        field_type = str(role_types.get(role) or "").upper()
        if not _IDENTIFIER_RE.fullmatch(column):
            raise ValueError(f"kpi_query_candidate_invalid_column:{role}")
        if field_type not in _NUMERIC_TYPES:
            raise ValueError(f"kpi_query_candidate_non_numeric_role:{role}:{field_type}")
        alias = "successful_orders" if role == "eligible_orders" else role
        selected.append(f"  SUM(CAST(`{column}` AS NUMERIC)) AS {alias}")
    return selected


def build_nsfr_query_candidate(
    *,
    candidate_id: str,
    manifest_approval: Mapping[str, object],
    semantic_mapping: Mapping[str, object],
) -> KpiQueryTemplateCandidate:
    """Generate a review artifact, never an executable registry entry.

    This minimal builder proves approved schema + measure semantics can generate SQL
    without guessed column names. Production filtering uses the stricter parameterized
    builder below, which additionally requires reviewed date/store dimensions.
    """

    table_id, _, role_map, role_types = _base_inputs(
        candidate_id=candidate_id,
        manifest_approval=manifest_approval,
        semantic_mapping=semantic_mapping,
    )
    selected = _measure_projection(role_map, role_types)
    sql = "SELECT\n" + ",\n".join(selected) + f"\nFROM `{table_id}`"
    return KpiQueryTemplateCandidate(
        candidate_id=candidate_id,
        metric_family="nsfr_family",
        table_id=table_id,
        sql=sql,
        parameter_names=(),
        schema_manifest_fingerprint=_sha(manifest_approval.get("manifest_fingerprint"), "manifest"),
        schema_approval_fingerprint=_sha(manifest_approval.get("approval_fingerprint"), "approval"),
        semantic_mapping_fingerprint=_sha(semantic_mapping.get("mapping_fingerprint"), "mapping"),
        executable=False,
    )


def build_parameterized_nsfr_query_candidate(
    *,
    candidate_id: str,
    manifest_approval: Mapping[str, object],
    semantic_mapping: Mapping[str, object],
    dimension_mapping: Mapping[str, object],
) -> KpiQueryTemplateCandidate:
    """Build a date/store-scoped NSFR review candidate with fully reviewed lineage.

    The candidate is deliberately non-executable. It may be reviewed into a registry
    entry only by a separate code change that pins every fingerprint and result contract.
    """

    table_id, evidence_fp, role_map, role_types = _base_inputs(
        candidate_id=candidate_id,
        manifest_approval=manifest_approval,
        semantic_mapping=semantic_mapping,
    )
    if dimension_mapping.get("verified") is not True:
        raise ValueError("kpi_query_candidate_dimension_mapping_required")
    if dimension_mapping.get("metric_family") != "nsfr_family":
        raise ValueError("kpi_query_candidate_dimension_family_mismatch")
    if str(dimension_mapping.get("table_id") or "") != table_id:
        raise ValueError("kpi_query_candidate_dimension_table_mismatch")
    if _sha(dimension_mapping.get("schema_evidence_fingerprint"), "dimension_evidence") != evidence_fp:
        raise ValueError("kpi_query_candidate_dimension_schema_evidence_mismatch")

    dim_roles = dimension_mapping.get("role_to_column")
    dim_types = dimension_mapping.get("role_types")
    if not isinstance(dim_roles, Mapping) or not isinstance(dim_types, Mapping):
        raise ValueError("kpi_query_candidate_dimension_mapping_required")
    date_column = str(dim_roles.get("date") or "")
    store_column = str(dim_roles.get("store") or "")
    date_type = str(dim_types.get("date") or "").upper()
    store_type = str(dim_types.get("store") or "").upper()
    if not _IDENTIFIER_RE.fullmatch(date_column):
        raise ValueError("kpi_query_candidate_invalid_dimension_column:date")
    if not _IDENTIFIER_RE.fullmatch(store_column):
        raise ValueError("kpi_query_candidate_invalid_dimension_column:store")
    if date_type not in _DATE_TYPES:
        raise ValueError(f"kpi_query_candidate_invalid_dimension_type:date:{date_type}")
    if store_type != "STRING":
        raise ValueError(f"kpi_query_candidate_invalid_dimension_type:store:{store_type}")

    selected = [
        f"  DATE(`{date_column}`) AS date",
        f"  `{store_column}` AS store",
        *_measure_projection(role_map, role_types),
    ]
    sql = (
        "SELECT\n"
        + ",\n".join(selected)
        + f"\nFROM `{table_id}`"
        + f"\nWHERE DATE(`{date_column}`) BETWEEN @start_date AND @end_date"
        + f"\n  AND (@stores_empty OR `{store_column}` IN UNNEST(@stores))"
        + "\nGROUP BY 1,2"
        + "\nORDER BY 1 DESC,2 ASC"
    )
    return KpiQueryTemplateCandidate(
        candidate_id=candidate_id,
        metric_family="nsfr_family",
        table_id=table_id,
        sql=sql,
        parameter_names=("start_date", "end_date", "stores", "stores_empty"),
        schema_manifest_fingerprint=_sha(manifest_approval.get("manifest_fingerprint"), "manifest"),
        schema_approval_fingerprint=_sha(manifest_approval.get("approval_fingerprint"), "approval"),
        semantic_mapping_fingerprint=_sha(semantic_mapping.get("mapping_fingerprint"), "mapping"),
        dimension_mapping_fingerprint=_sha(dimension_mapping.get("mapping_fingerprint"), "dimension_mapping"),
        executable=False,
    )
