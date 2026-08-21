from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .kpi_schema_evidence import KpiSchemaEvidence

NSFR_DIMENSION_ROLES = ("date", "store")
_ALLOWED_DATE_TYPES = {"DATE", "DATETIME", "TIMESTAMP"}
_ALLOWED_STORE_TYPES = {"STRING"}


@dataclass(frozen=True)
class KpiDimensionRoleMapping:
    metric_family: str
    table_id: str
    role_to_column: Mapping[str, str]
    schema_evidence_fingerprint: str
    reviewed_at: str
    reviewer: str | None = None
    reviewed: bool = False

    @property
    def canonical_mapping(self) -> dict[str, str]:
        return {
            str(role).strip().lower(): str(column).strip().lower()
            for role, column in sorted(self.role_to_column.items())
        }

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric_family": self.metric_family,
            "table_id": self.table_id,
            "role_to_column": self.canonical_mapping,
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "reviewed": self.reviewed,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_review_time(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("kpi_dimension_mapping_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("kpi_dimension_mapping_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("kpi_dimension_mapping_future_review_time")


def verify_nsfr_dimension_mapping(
    evidence: KpiSchemaEvidence,
    mapping: KpiDimensionRoleMapping,
) -> dict[str, object]:
    """Human-review the exact date/store dimensions used by NSFR-family filters.

    Schema presence is not semantic proof. The mapping must bind to the same reviewed
    schema evidence used by the KPI measure mapping; guessed aliases are rejected.
    """

    expected_table = "report_dmart_ops_nsfr_global_overview"
    if mapping.metric_family != "nsfr_family":
        raise ValueError("kpi_dimension_mapping_metric_family_mismatch")
    if evidence.table_id != expected_table or mapping.table_id != expected_table:
        raise ValueError("kpi_dimension_mapping_table_mismatch")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("kpi_dimension_mapping_reviewed_schema_evidence_required")
    if mapping.schema_evidence_fingerprint != evidence.fingerprint:
        raise ValueError("kpi_dimension_mapping_schema_evidence_mismatch")
    if not mapping.reviewed or not (mapping.reviewer or "").strip():
        raise ValueError("kpi_dimension_mapping_human_review_required")
    _validate_review_time(mapping.reviewed_at)

    observed = evidence.canonical_columns
    role_map = mapping.canonical_mapping
    missing = sorted(set(NSFR_DIMENSION_ROLES) - set(role_map))
    if missing:
        raise ValueError("kpi_dimension_mapping_missing_roles:" + ",".join(missing))

    date_column = role_map["date"]
    store_column = role_map["store"]
    if date_column == store_column:
        raise ValueError("kpi_dimension_mapping_duplicate_columns")
    for role, column in (("date", date_column), ("store", store_column)):
        if not column:
            raise ValueError(f"kpi_dimension_mapping_blank_column:{role}")
        if column not in observed:
            raise ValueError(f"kpi_dimension_mapping_unobserved_column:{role}:{column}")

    date_type = observed[date_column]
    store_type = observed[store_column]
    if date_type not in _ALLOWED_DATE_TYPES:
        raise ValueError(f"kpi_dimension_mapping_invalid_date_type:{date_type}")
    if store_type not in _ALLOWED_STORE_TYPES:
        raise ValueError(f"kpi_dimension_mapping_invalid_store_type:{store_type}")

    return {
        "metric_family": "nsfr_family",
        "table_id": expected_table,
        "role_to_column": {"date": date_column, "store": store_column},
        "role_types": {"date": date_type, "store": store_type},
        "schema_evidence_fingerprint": evidence.fingerprint,
        "mapping_fingerprint": mapping.fingerprint,
        "reviewer": mapping.reviewer,
        "reviewed_at": mapping.reviewed_at,
        "verified": True,
    }
