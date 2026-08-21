from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from .kpi_activation_gate import KpiNsfrActivationBundle
from .kpi_query_candidate import KpiQueryTemplateCandidate
from .kpi_result_validation import KpiResultContract


@dataclass(frozen=True)
class NsfrTemplateActivationReview:
    metric: str
    schema_evidence_fingerprint: str
    schema_manifest_fingerprint: str
    schema_approval_fingerprint: str
    semantic_mapping_fingerprint: str
    dimension_mapping_fingerprint: str
    result_contract_fingerprint: str
    query_candidate_fingerprint: str
    executable: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "schema_manifest_fingerprint": self.schema_manifest_fingerprint,
            "schema_approval_fingerprint": self.schema_approval_fingerprint,
            "semantic_mapping_fingerprint": self.semantic_mapping_fingerprint,
            "dimension_mapping_fingerprint": self.dimension_mapping_fingerprint,
            "result_contract_fingerprint": self.result_contract_fingerprint,
            "query_candidate_fingerprint": self.query_candidate_fingerprint,
            "executable": self.executable,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"nsfr_template_gate_invalid_fingerprint:{field}")
    return text


def verify_nsfr_template_activation_review(
    *,
    activation: KpiNsfrActivationBundle,
    manifest_approval: Mapping[str, object],
    dimension_mapping: Mapping[str, object],
    query_candidate: KpiQueryTemplateCandidate,
    result_contract: KpiResultContract,
) -> NsfrTemplateActivationReview:
    """Seal all reviewed NSFR template lineage into one non-executable review artifact.

    This is intentionally not a registry mutation or production activation. It proves a
    future reviewed registry entry can be traced to one exact schema observation,
    approval, measure mapping, dimension mapping, result contract and SQL candidate.
    """

    if activation.metric not in {"nsfr", "pfr", "refund"}:
        raise ValueError("nsfr_template_gate_metric_not_supported")
    if manifest_approval.get("verified") is not True:
        raise ValueError("nsfr_template_gate_manifest_approval_required")
    if dimension_mapping.get("verified") is not True:
        raise ValueError("nsfr_template_gate_dimension_mapping_required")
    if dimension_mapping.get("metric_family") != "nsfr_family":
        raise ValueError("nsfr_template_gate_dimension_family_mismatch")
    if query_candidate.metric_family != "nsfr_family":
        raise ValueError("nsfr_template_gate_candidate_family_mismatch")
    if query_candidate.executable:
        raise ValueError("nsfr_template_gate_candidate_must_be_non_executable")
    if query_candidate.parameter_names != ("start_date", "end_date", "stores", "stores_empty"):
        raise ValueError("nsfr_template_gate_parameter_contract_mismatch")

    evidence_fp = _sha(activation.schema_evidence_fingerprint, "activation_evidence")
    if _sha(manifest_approval.get("evidence_fingerprint"), "manifest_evidence") != evidence_fp:
        raise ValueError("nsfr_template_gate_manifest_evidence_mismatch")
    if _sha(dimension_mapping.get("schema_evidence_fingerprint"), "dimension_evidence") != evidence_fp:
        raise ValueError("nsfr_template_gate_dimension_evidence_mismatch")

    manifest_fp = _sha(manifest_approval.get("manifest_fingerprint"), "manifest")
    approval_fp = _sha(manifest_approval.get("approval_fingerprint"), "approval")
    dimension_fp = _sha(dimension_mapping.get("mapping_fingerprint"), "dimension_mapping")
    if query_candidate.schema_manifest_fingerprint != manifest_fp:
        raise ValueError("nsfr_template_gate_candidate_manifest_mismatch")
    if query_candidate.schema_approval_fingerprint != approval_fp:
        raise ValueError("nsfr_template_gate_candidate_approval_mismatch")
    if query_candidate.semantic_mapping_fingerprint != activation.semantic_mapping_fingerprint:
        raise ValueError("nsfr_template_gate_candidate_semantic_mapping_mismatch")
    if query_candidate.dimension_mapping_fingerprint != dimension_fp:
        raise ValueError("nsfr_template_gate_candidate_dimension_mapping_mismatch")

    if result_contract.metric != activation.metric:
        raise ValueError("nsfr_template_gate_result_metric_mismatch")
    if result_contract.fingerprint != activation.result_contract_fingerprint:
        raise ValueError("nsfr_template_gate_result_contract_mismatch")

    return NsfrTemplateActivationReview(
        metric=activation.metric,
        schema_evidence_fingerprint=evidence_fp,
        schema_manifest_fingerprint=manifest_fp,
        schema_approval_fingerprint=approval_fp,
        semantic_mapping_fingerprint=activation.semantic_mapping_fingerprint,
        dimension_mapping_fingerprint=dimension_fp,
        result_contract_fingerprint=activation.result_contract_fingerprint,
        query_candidate_fingerprint=query_candidate.fingerprint,
        executable=False,
    )
