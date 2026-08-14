from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .kpi_schema_evidence import KpiSchemaEvidence


NSFR_FAMILY_REQUIRED_ROLES = (
    "eligible_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)


@dataclass(frozen=True)
class KpiSemanticRoleMapping:
    """Human-reviewed mapping from business roles to observed production columns.

    Column names are intentionally not inferred from metric names. A schema observation
    proves only that columns exist; this mapping separately proves which observed
    column carries each business meaning required by the KPI contract.
    """

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
        raise ValueError("kpi_semantic_mapping_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("kpi_semantic_mapping_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("kpi_semantic_mapping_future_review_time")


def verify_semantic_role_mapping(
    evidence: KpiSchemaEvidence,
    mapping: KpiSemanticRoleMapping,
    *,
    expected_table: str,
    required_roles: tuple[str, ...],
) -> dict[str, object]:
    """Bind reviewed business roles to one exact reviewed schema observation.

    This gate deliberately refuses guessed column names, stale schema evidence and
    role aliasing. It does not activate the KPI by itself; activation still requires
    semantic/schema/unit/aggregation/result contracts.
    """

    if mapping.table_id != expected_table or evidence.table_id != expected_table:
        raise ValueError("kpi_semantic_mapping_table_mismatch")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("kpi_semantic_mapping_reviewed_schema_evidence_required")
    if mapping.schema_evidence_fingerprint != evidence.fingerprint:
        raise ValueError("kpi_semantic_mapping_schema_evidence_mismatch")
    if not mapping.reviewed or not (mapping.reviewer or "").strip():
        raise ValueError("kpi_semantic_mapping_human_review_required")
    _validate_review_time(mapping.reviewed_at)

    observed = evidence.canonical_columns
    role_map = mapping.canonical_mapping
    missing_roles = sorted(set(required_roles) - set(role_map))
    if missing_roles:
        raise ValueError("kpi_semantic_mapping_missing_roles:" + ",".join(missing_roles))

    blank_columns = sorted(role for role in required_roles if not role_map[role])
    if blank_columns:
        raise ValueError("kpi_semantic_mapping_blank_columns:" + ",".join(blank_columns))

    selected_columns = [role_map[role] for role in required_roles]
    duplicates = sorted({name for name in selected_columns if selected_columns.count(name) > 1})
    if duplicates:
        raise ValueError("kpi_semantic_mapping_duplicate_columns:" + ",".join(duplicates))

    unknown_columns = sorted({name for name in selected_columns if name not in observed})
    if unknown_columns:
        raise ValueError("kpi_semantic_mapping_unobserved_columns:" + ",".join(unknown_columns))

    untyped_columns = sorted({name for name in selected_columns if not observed[name].strip()})
    if untyped_columns:
        raise ValueError("kpi_semantic_mapping_untyped_columns:" + ",".join(untyped_columns))

    return {
        "metric_family": mapping.metric_family,
        "table_id": expected_table,
        "role_to_column": {role: role_map[role] for role in required_roles},
        "role_types": {role: observed[role_map[role]] for role in required_roles},
        "schema_evidence_fingerprint": evidence.fingerprint,
        "mapping_fingerprint": mapping.fingerprint,
        "reviewer": mapping.reviewer,
        "reviewed_at": mapping.reviewed_at,
        "verified": True,
    }


def verify_nsfr_family_role_mapping(
    evidence: KpiSchemaEvidence,
    mapping: KpiSemanticRoleMapping,
) -> dict[str, object]:
    if mapping.metric_family != "nsfr_family":
        raise ValueError("kpi_semantic_mapping_metric_family_mismatch")
    return verify_semantic_role_mapping(
        evidence,
        mapping,
        expected_table="report_dmart_ops_nsfr_global_overview",
        required_roles=NSFR_FAMILY_REQUIRED_ROLES,
    )
