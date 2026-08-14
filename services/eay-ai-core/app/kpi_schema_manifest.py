from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .kpi_schema_evidence import KpiSchemaEvidence


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _validate_timestamp(value: str, *, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"kpi_schema_manifest_invalid_timestamp:{field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"kpi_schema_manifest_timezone_required:{field}")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError(f"kpi_schema_manifest_future_timestamp:{field}")


@dataclass(frozen=True)
class KpiSchemaEvidenceManifest:
    manifest_id: str
    table_id: str
    evidence_fingerprint: str
    observed_columns: Mapping[str, str]
    captured_at: str
    source: str

    @property
    def canonical_columns(self) -> dict[str, str]:
        return {
            str(name).strip().lower(): str(field_type).strip().upper()
            for name, field_type in sorted(self.observed_columns.items())
        }

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "manifest_id": self.manifest_id,
                "table_id": self.table_id,
                "evidence_fingerprint": self.evidence_fingerprint,
                "observed_columns": self.canonical_columns,
                "captured_at": self.captured_at,
                "source": self.source,
            }
        )


@dataclass(frozen=True)
class KpiSchemaManifestApproval:
    manifest_fingerprint: str
    approval_ref: str
    reviewer: str
    approved_at: str

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "manifest_fingerprint": self.manifest_fingerprint,
                "approval_ref": self.approval_ref,
                "reviewer": self.reviewer,
                "approved_at": self.approved_at,
            }
        )


def build_schema_evidence_manifest(
    *,
    manifest_id: str,
    evidence: KpiSchemaEvidence,
) -> KpiSchemaEvidenceManifest:
    if not manifest_id.strip():
        raise ValueError("kpi_schema_manifest_id_required")
    if not evidence.reviewed or not (evidence.reviewer or "").strip():
        raise ValueError("kpi_schema_manifest_reviewed_evidence_required")
    if not evidence.source.strip():
        raise ValueError("kpi_schema_manifest_source_required")
    _validate_timestamp(evidence.captured_at, field="captured_at")
    columns = evidence.canonical_columns
    if not columns:
        raise ValueError("kpi_schema_manifest_columns_required")
    if any(not name or not field_type for name, field_type in columns.items()):
        raise ValueError("kpi_schema_manifest_invalid_columns")
    return KpiSchemaEvidenceManifest(
        manifest_id=manifest_id,
        table_id=evidence.table_id,
        evidence_fingerprint=evidence.fingerprint,
        observed_columns=columns,
        captured_at=evidence.captured_at,
        source=evidence.source,
    )


def verify_schema_manifest_approval(
    manifest: KpiSchemaEvidenceManifest,
    approval: KpiSchemaManifestApproval,
) -> dict[str, str | bool]:
    if approval.manifest_fingerprint != manifest.fingerprint:
        raise ValueError("kpi_schema_manifest_approval_manifest_mismatch")
    if not approval.approval_ref.strip():
        raise ValueError("kpi_schema_manifest_approval_ref_required")
    if not approval.reviewer.strip():
        raise ValueError("kpi_schema_manifest_approval_reviewer_required")
    _validate_timestamp(approval.approved_at, field="approved_at")
    return {
        "manifest_id": manifest.manifest_id,
        "table_id": manifest.table_id,
        "evidence_fingerprint": manifest.evidence_fingerprint,
        "manifest_fingerprint": manifest.fingerprint,
        "approval_fingerprint": approval.fingerprint,
        "approval_ref": approval.approval_ref,
        "reviewer": approval.reviewer,
        "verified": True,
    }
