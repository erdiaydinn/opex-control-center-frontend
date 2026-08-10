from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


NSFR_FAMILY_REQUIRED_COLUMNS = (
    "successful_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)


@dataclass(frozen=True)
class KpiSchemaEvidence:
    table_id: str
    observed_columns: Mapping[str, str]
    captured_at: str
    source: str
    reviewer: str | None = None
    reviewed: bool = False

    @property
    def canonical_columns(self) -> dict[str, str]:
        return {
            str(name).lower(): str(field_type).upper()
            for name, field_type in sorted(self.observed_columns.items())
        }

    @property
    def fingerprint(self) -> str:
        payload = {
            "table_id": self.table_id,
            "observed_columns": self.canonical_columns,
            "captured_at": self.captured_at,
            "source": self.source,
            "reviewer": self.reviewer,
            "reviewed": self.reviewed,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_capture_time(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("kpi_schema_evidence_invalid_capture_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("kpi_schema_evidence_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("kpi_schema_evidence_future_capture_time")


def verify_schema_evidence(
    evidence: KpiSchemaEvidence,
    *,
    expected_table: str,
    required_columns: tuple[str, ...],
) -> dict[str, object]:
    """Validate a human-reviewed production schema observation before contract pinning.

    This does not activate a KPI. It proves only that a reviewed, timestamped schema
    observation contains the required production columns. Exact BigQuery types remain
    part of the evidence fingerprint so a later contract can pin them without guessing.
    """

    if evidence.table_id != expected_table:
        raise ValueError("kpi_schema_evidence_table_mismatch")
    if not evidence.source.strip():
        raise ValueError("kpi_schema_evidence_source_required")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("kpi_schema_evidence_human_review_required")
    _validate_capture_time(evidence.captured_at)

    columns = evidence.canonical_columns
    missing = sorted(set(required_columns) - set(columns))
    if missing:
        raise ValueError("kpi_schema_evidence_missing_columns:" + ",".join(missing))

    blank_types = sorted(name for name in required_columns if not columns[name].strip())
    if blank_types:
        raise ValueError("kpi_schema_evidence_type_required:" + ",".join(blank_types))

    return {
        "table_id": evidence.table_id,
        "required_columns": list(required_columns),
        "column_types": {name: columns[name] for name in required_columns},
        "captured_at": evidence.captured_at,
        "source": evidence.source,
        "reviewer": evidence.reviewer,
        "fingerprint": evidence.fingerprint,
        "verified": True,
    }


def verify_nsfr_schema_evidence(evidence: KpiSchemaEvidence) -> dict[str, object]:
    return verify_schema_evidence(
        evidence,
        expected_table="report_dmart_ops_nsfr_global_overview",
        required_columns=NSFR_FAMILY_REQUIRED_COLUMNS,
    )
