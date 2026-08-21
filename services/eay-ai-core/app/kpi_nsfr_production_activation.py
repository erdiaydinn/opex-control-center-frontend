from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .kpi_activation_gate import KpiNsfrActivationBundle
from .kpi_query_candidate import KpiQueryTemplateCandidate


EXPECTED_NSFR_PARAMETERS = ("start_date", "end_date", "stores", "stores_empty")


@dataclass(frozen=True)
class NsfrProductionActivationArtifact:
    """Human-reviewed, immutable bridge from governed KPI evidence to registry review.

    This artifact is deliberately *not* an executable registry entry. It proves that
    semantic/schema evidence, schema approval, measure mapping, dimension mapping,
    result reconciliation and the generated SQL candidate all refer to one lineage.
    A later explicit code review may pin the artifact fingerprint into a query registry.
    """

    metric: str
    candidate_id: str
    candidate_fingerprint: str
    table_id: str
    semantic_fingerprint: str
    schema_fingerprint: str
    schema_evidence_fingerprint: str
    schema_manifest_fingerprint: str
    schema_approval_fingerprint: str
    semantic_mapping_fingerprint: str
    dimension_mapping_fingerprint: str
    result_contract_fingerprint: str
    reviewed_at: str
    reviewer: str
    approval_reference: str
    approved_for_registry_review: bool = True
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "candidate_id": self.candidate_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "table_id": self.table_id,
            "semantic_fingerprint": self.semantic_fingerprint,
            "schema_fingerprint": self.schema_fingerprint,
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "schema_manifest_fingerprint": self.schema_manifest_fingerprint,
            "schema_approval_fingerprint": self.schema_approval_fingerprint,
            "semantic_mapping_fingerprint": self.semantic_mapping_fingerprint,
            "dimension_mapping_fingerprint": self.dimension_mapping_fingerprint,
            "result_contract_fingerprint": self.result_contract_fingerprint,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "approval_reference": self.approval_reference,
            "approved_for_registry_review": self.approved_for_registry_review,
            "executable": self.executable,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"nsfr_production_activation_invalid_fingerprint:{field}")
    return text


def _review_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("nsfr_production_activation_invalid_review_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("nsfr_production_activation_timezone_required")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("nsfr_production_activation_future_review_time")
    return value


def seal_nsfr_production_activation(
    *,
    metric: str,
    activation: KpiNsfrActivationBundle,
    manifest_approval: Mapping[str, object],
    semantic_mapping: Mapping[str, object],
    dimension_mapping: Mapping[str, object],
    candidate: KpiQueryTemplateCandidate,
    reviewer: str,
    reviewed_at: str,
    approval_reference: str,
) -> NsfrProductionActivationArtifact:
    """Seal all reviewed NSFR-family lineage into a non-executable approval artifact."""

    if metric not in {"nsfr", "pfr", "refund"} or activation.metric != metric:
        raise ValueError("nsfr_production_activation_metric_mismatch")
    if not reviewer.strip() or not approval_reference.strip():
        raise ValueError("nsfr_production_activation_human_approval_required")
    _review_time(reviewed_at)

    if manifest_approval.get("verified") is not True:
        raise ValueError("nsfr_production_activation_schema_approval_required")
    if semantic_mapping.get("verified") is not True:
        raise ValueError("nsfr_production_activation_semantic_mapping_required")
    if dimension_mapping.get("verified") is not True:
        raise ValueError("nsfr_production_activation_dimension_mapping_required")

    evidence_fp = _sha(activation.schema_evidence_fingerprint, "schema_evidence")
    if evidence_fp != _sha(manifest_approval.get("evidence_fingerprint"), "manifest_evidence"):
        raise ValueError("nsfr_production_activation_manifest_schema_mismatch")
    if evidence_fp != _sha(semantic_mapping.get("schema_evidence_fingerprint"), "semantic_evidence"):
        raise ValueError("nsfr_production_activation_semantic_schema_mismatch")
    if evidence_fp != _sha(dimension_mapping.get("schema_evidence_fingerprint"), "dimension_evidence"):
        raise ValueError("nsfr_production_activation_dimension_schema_mismatch")

    semantic_mapping_fp = _sha(semantic_mapping.get("mapping_fingerprint"), "semantic_mapping")
    if semantic_mapping_fp != activation.semantic_mapping_fingerprint:
        raise ValueError("nsfr_production_activation_semantic_mapping_mismatch")
    dimension_mapping_fp = _sha(dimension_mapping.get("mapping_fingerprint"), "dimension_mapping")

    if candidate.executable:
        raise ValueError("nsfr_production_activation_candidate_must_be_non_executable")
    if candidate.metric_family != "nsfr_family":
        raise ValueError("nsfr_production_activation_candidate_family_mismatch")
    if tuple(candidate.parameter_names) != EXPECTED_NSFR_PARAMETERS:
        raise ValueError("nsfr_production_activation_candidate_parameter_contract_mismatch")

    table_id = str(manifest_approval.get("table_id") or "")
    if not table_id or candidate.table_id != table_id:
        raise ValueError("nsfr_production_activation_candidate_table_mismatch")
    if candidate.schema_manifest_fingerprint != _sha(manifest_approval.get("manifest_fingerprint"), "manifest"):
        raise ValueError("nsfr_production_activation_candidate_manifest_mismatch")
    if candidate.schema_approval_fingerprint != _sha(manifest_approval.get("approval_fingerprint"), "approval"):
        raise ValueError("nsfr_production_activation_candidate_approval_mismatch")
    if candidate.semantic_mapping_fingerprint != semantic_mapping_fp:
        raise ValueError("nsfr_production_activation_candidate_semantic_mapping_mismatch")
    if candidate.dimension_mapping_fingerprint != dimension_mapping_fp:
        raise ValueError("nsfr_production_activation_candidate_dimension_mapping_mismatch")

    return NsfrProductionActivationArtifact(
        metric=metric,
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.fingerprint,
        table_id=table_id,
        semantic_fingerprint=_sha(activation.semantic_fingerprint, "semantic"),
        schema_fingerprint=_sha(activation.schema_fingerprint, "schema"),
        schema_evidence_fingerprint=evidence_fp,
        schema_manifest_fingerprint=candidate.schema_manifest_fingerprint,
        schema_approval_fingerprint=candidate.schema_approval_fingerprint,
        semantic_mapping_fingerprint=semantic_mapping_fp,
        dimension_mapping_fingerprint=dimension_mapping_fp,
        result_contract_fingerprint=_sha(activation.result_contract_fingerprint, "result_contract"),
        reviewed_at=reviewed_at,
        reviewer=reviewer.strip(),
        approval_reference=approval_reference.strip(),
        approved_for_registry_review=True,
        executable=False,
    )
