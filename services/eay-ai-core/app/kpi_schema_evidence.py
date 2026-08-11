from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


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
    required_columns: tuple[str, ...] = (),
) -> dict[str, object]:
    """Validate a human-reviewed production schema observation without inventing semantics.

    INFORMATION_SCHEMA proves which columns/types exist at one point in time. It does not
    prove that a column means PFR, refund, eligible orders, prep duration, or any other
    business concept. Business-role binding is therefore a separate reviewed mapping gate.
    `required_columns` is reserved for genuinely structural names already guaranteed by a
    source contract; KPI semantic roles must not be passed through this argument.
    """

    if evidence.table_id != expected_table:
        raise ValueError("kpi_schema_evidence_table_mismatch")
    if not evidence.source.strip():
        raise ValueError("kpi_schema_evidence_source_required")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("kpi_schema_evidence_human_review_required")
    _validate_capture_time(evidence.captured_at)

    columns = evidence.canonical_columns
    if not columns:
        raise ValueError("kpi_schema_evidence_empty_schema")
    blank_names = sorted(name for name in columns if not name.strip())
    if blank_names:
        raise ValueError("kpi_schema_evidence_column_name_required")
    blank_types = sorted(name for name, field_type in columns.items() if not field_type.strip())
    if blank_types:
        raise ValueError("kpi_schema_evidence_type_required:" + ",".join(blank_types))

    missing = sorted(set(required_columns) - set(columns))
    if missing:
        raise ValueError("kpi_schema_evidence_missing_columns:" + ",".join(missing))

    projected = (
        {name: columns[name] for name in required_columns}
        if required_columns
        else dict(columns)
    )
    return {
        "table_id": evidence.table_id,
        "observed_columns": dict(columns),
        "required_columns": list(required_columns),
        "column_types": projected,
        "captured_at": evidence.captured_at,
        "source": evidence.source,
        "reviewer": evidence.reviewer,
        "fingerprint": evidence.fingerprint,
        "verified": True,
    }


def verify_nsfr_schema_evidence(evidence: KpiSchemaEvidence) -> dict[str, object]:
    """Verify only the NSFR source-table observation, not KPI business meaning.

    Actual NSFR/PFR/Refund role-to-column semantics must be supplied through
    `verify_nsfr_family_role_mapping`; accepting guessed canonical names here would make
    the human semantic-mapping gate circular and unsafe.
    """

    return verify_schema_evidence(
        evidence,
        expected_table="report_dmart_ops_nsfr_global_overview",
    )
