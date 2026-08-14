from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .kpi_schema_evidence import KpiSchemaEvidence

PUTAWAY_REQUIRED_ROLES = (
    "date",
    "city",
    "inbound_kind",
    "elapsed_minutes",
    "initial_qty",
    "on_shelf_qty",
)

_DATE_TYPES = {"DATE", "DATETIME", "TIMESTAMP"}
_STRING_TYPES = {"STRING"}
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


@dataclass(frozen=True)
class PutawaySourceRoleMapping:
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
            "metric": "putaway",
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
        raise ValueError("putaway_source_mapping_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("putaway_source_mapping_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("putaway_source_mapping_future_review_time")


def verify_putaway_source_mapping(
    evidence: KpiSchemaEvidence,
    mapping: PutawaySourceRoleMapping,
) -> dict[str, object]:
    """Bind putaway business roles to one exact reviewed production schema snapshot.

    The mapping intentionally separates raw-column existence from business meaning.
    Inbound kind, elapsed time, city and quantity roles must be reviewed explicitly;
    names are never guessed from convenient aliases.
    """

    expected_table = "dmart_ops_st_po_receiving_putaway_sku_details"
    if evidence.table_id != expected_table or mapping.table_id != expected_table:
        raise ValueError("putaway_source_mapping_table_mismatch")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("putaway_source_mapping_reviewed_schema_evidence_required")
    if mapping.schema_evidence_fingerprint != evidence.fingerprint:
        raise ValueError("putaway_source_mapping_schema_evidence_mismatch")
    if not mapping.reviewed or not (mapping.reviewer or "").strip():
        raise ValueError("putaway_source_mapping_human_review_required")
    _validate_review_time(mapping.reviewed_at)

    observed = evidence.canonical_columns
    role_map = mapping.canonical_mapping
    missing = sorted(set(PUTAWAY_REQUIRED_ROLES) - set(role_map))
    if missing:
        raise ValueError("putaway_source_mapping_missing_roles:" + ",".join(missing))

    selected = [role_map[role] for role in PUTAWAY_REQUIRED_ROLES]
    if any(not value for value in selected):
        raise ValueError("putaway_source_mapping_blank_column")
    duplicates = sorted({name for name in selected if selected.count(name) > 1})
    if duplicates:
        raise ValueError("putaway_source_mapping_duplicate_columns:" + ",".join(duplicates))

    unknown = sorted({name for name in selected if name not in observed})
    if unknown:
        raise ValueError("putaway_source_mapping_unobserved_columns:" + ",".join(unknown))

    expected_types = {
        "date": _DATE_TYPES,
        "city": _STRING_TYPES,
        "inbound_kind": _STRING_TYPES,
        "elapsed_minutes": _NUMERIC_TYPES,
        "initial_qty": _NUMERIC_TYPES,
        "on_shelf_qty": _NUMERIC_TYPES,
    }
    role_types: dict[str, str] = {}
    for role in PUTAWAY_REQUIRED_ROLES:
        field_type = observed[role_map[role]].upper()
        role_types[role] = field_type
        if field_type not in expected_types[role]:
            raise ValueError(
                f"putaway_source_mapping_invalid_type:{role}:{field_type}"
            )

    return {
        "metric": "putaway",
        "table_id": expected_table,
        "role_to_column": {role: role_map[role] for role in PUTAWAY_REQUIRED_ROLES},
        "role_types": role_types,
        "schema_evidence_fingerprint": evidence.fingerprint,
        "mapping_fingerprint": mapping.fingerprint,
        "reviewer": mapping.reviewer,
        "reviewed_at": mapping.reviewed_at,
        "verified": True,
    }
