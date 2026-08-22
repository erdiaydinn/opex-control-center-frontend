"""Bridge company detection coverage into EAY platform security assurance.

The platform-assurance plan, global threat enrichment and company telemetry
coverage remain separate canonical artifacts. This bridge binds their exact
fingerprints into one audit-friendly finding without granting release,
remediation, deployment or execution authority.

COVERED may verify the detection-coverage control. PARTIAL is a failure.
UNVERIFIED stays inconclusive: missing evidence is never silently converted into a
confirmed detection gap or a pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.company_detection_coverage_intelligence import (
    CompanyDetectionCoverageReceipt,
    CompanyDetectionCoverageStatus,
)
from app.cyber_platform_assurance import (
    SecurityAssuranceEnvironment,
    SecurityAssurancePlan,
    SecurityAssuranceStatus,
    SecurityFindingSeverity,
)
from app.cyber_threat_enrichment_intelligence import (
    GlobalDefensiveUrgency,
    GlobalThreatEnrichmentReceipt,
)

CYBER_DETECTION_ASSURANCE_CONTRACT = "eay-cyber-detection-assurance-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class CyberDetectionAssuranceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DETECTION_ASSURANCE_CONTRACT
    finding_id: str = Field(min_length=1)
    identity: CompanyIdentity
    assurance_plan_id: str = Field(min_length=1)
    assurance_plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    assurance_environment: SecurityAssuranceEnvironment
    global_enrichment_receipt_id: str = Field(min_length=1)
    global_enrichment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_detection_coverage_receipt_id: str = Field(min_length=1)
    company_detection_coverage_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    cve_id: str
    status: SecurityAssuranceStatus
    severity: SecurityFindingSeverity
    required_data_component_ids: tuple[str, ...]
    missing_component_ids: tuple[str, ...]
    degraded_component_ids: tuple[str, ...]
    unverified_component_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    control_verified: bool
    security_attention_required: bool
    production_write_allowed: bool = False
    automatic_remediation_allowed: bool = False
    release_gate_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def finding_is_evidence_bound_and_non_authoritative(
        self,
    ) -> CyberDetectionAssuranceFinding:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if self.control_verified != (self.status is SecurityAssuranceStatus.PASS):
            raise ValueError("cyber_detection_assurance_pass_flag_mismatch")
        if self.status is SecurityAssuranceStatus.PASS and (
            self.missing_component_ids
            or self.degraded_component_ids
            or self.unverified_component_ids
        ):
            raise ValueError("cyber_detection_assurance_pass_cannot_have_gaps")
        if self.status is SecurityAssuranceStatus.FAIL and not (
            self.missing_component_ids or self.degraded_component_ids
        ):
            raise ValueError("cyber_detection_assurance_fail_requires_confirmed_gap")
        if self.status is SecurityAssuranceStatus.INCONCLUSIVE and self.control_verified:
            raise ValueError("cyber_detection_assurance_inconclusive_cannot_verify_control")
        if self.production_write_allowed:
            raise ValueError("cyber_detection_assurance_production_write_forbidden")
        if self.automatic_remediation_allowed:
            raise ValueError("cyber_detection_assurance_auto_remediation_forbidden")
        if self.release_gate_authority_granted:
            raise ValueError("cyber_detection_assurance_never_grants_release_authority")
        if self.execution_authority_granted:
            raise ValueError("cyber_detection_assurance_never_grants_execution_authority")
        for values in (
            self.required_data_component_ids,
            self.missing_component_ids,
            self.degraded_component_ids,
            self.unverified_component_ids,
            self.evidence_refs,
        ):
            if len(values) != len(set(values)):
                raise ValueError("cyber_detection_assurance_references_must_be_unique")
        for ref in (
            self.finding_id,
            self.assurance_plan_id,
            self.global_enrichment_receipt_id,
            self.company_detection_coverage_receipt_id,
            *self.evidence_refs,
        ):
            _safe_ref(ref, "cyber_detection_assurance_unsafe_reference_forbidden")
        _verify(self, "cyber_detection_assurance_fingerprint_mismatch")
        return self


def build_cyber_detection_assurance_finding(
    *,
    identity: CompanyIdentity,
    assurance_plan: SecurityAssurancePlan,
    global_enrichment: GlobalThreatEnrichmentReceipt,
    company_detection_coverage: CompanyDetectionCoverageReceipt,
) -> CyberDetectionAssuranceFinding:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    plan = SecurityAssurancePlan.model_validate(assurance_plan.model_dump(mode="json"))
    global_enrichment = GlobalThreatEnrichmentReceipt.model_validate(
        global_enrichment.model_dump(mode="json")
    )
    coverage = CompanyDetectionCoverageReceipt.model_validate(
        company_detection_coverage.model_dump(mode="json")
    )
    if coverage.identity.fingerprint != identity.fingerprint:
        raise ValueError("cyber_detection_assurance_company_identity_mismatch")
    if coverage.global_enrichment_receipt_id != global_enrichment.receipt_id:
        raise ValueError("cyber_detection_assurance_global_receipt_id_mismatch")
    if coverage.global_enrichment_fingerprint != global_enrichment.fingerprint:
        raise ValueError("cyber_detection_assurance_global_fingerprint_mismatch")
    if coverage.cve_id != global_enrichment.cve_id:
        raise ValueError("cyber_detection_assurance_cve_mismatch")

    if coverage.coverage_status is CompanyDetectionCoverageStatus.COVERED:
        status = SecurityAssuranceStatus.PASS
        severity = SecurityFindingSeverity.INFO
        attention = False
    elif coverage.coverage_status is CompanyDetectionCoverageStatus.PARTIAL:
        status = SecurityAssuranceStatus.FAIL
        severity = _gap_severity(global_enrichment.global_defensive_urgency)
        attention = True
    elif coverage.coverage_status is CompanyDetectionCoverageStatus.UNVERIFIED:
        status = SecurityAssuranceStatus.INCONCLUSIVE
        severity = _unverified_severity(global_enrichment.global_defensive_urgency)
        attention = True
    else:
        status = SecurityAssuranceStatus.INCONCLUSIVE
        severity = SecurityFindingSeverity.INFO
        attention = False

    evidence_refs = (
        f"assurance-plan:{plan.plan_id}:{plan.fingerprint[:16]}",
        f"global-threat-enrichment:{global_enrichment.receipt_id}",
        f"company-detection-coverage:{coverage.receipt_id}",
    )
    seed = {
        "identity": identity.fingerprint,
        "plan": plan.fingerprint,
        "global": global_enrichment.fingerprint,
        "coverage": coverage.fingerprint,
    }
    finding_id = f"cyber-detection-assurance:{_fingerprint(seed)[:24]}"
    draft = {
        "contract": CYBER_DETECTION_ASSURANCE_CONTRACT,
        "finding_id": finding_id,
        "identity": identity.model_dump(mode="json"),
        "assurance_plan_id": plan.plan_id,
        "assurance_plan_fingerprint": plan.fingerprint,
        "assurance_environment": plan.environment.value,
        "global_enrichment_receipt_id": global_enrichment.receipt_id,
        "global_enrichment_fingerprint": global_enrichment.fingerprint,
        "company_detection_coverage_receipt_id": coverage.receipt_id,
        "company_detection_coverage_fingerprint": coverage.fingerprint,
        "cve_id": coverage.cve_id,
        "status": status.value,
        "severity": severity.value,
        "required_data_component_ids": list(coverage.required_data_component_ids),
        "missing_component_ids": list(coverage.missing_component_ids),
        "degraded_component_ids": list(coverage.degraded_component_ids),
        "unverified_component_ids": list(coverage.unverified_component_ids),
        "evidence_refs": list(evidence_refs),
        "control_verified": status is SecurityAssuranceStatus.PASS,
        "security_attention_required": attention,
        "production_write_allowed": False,
        "automatic_remediation_allowed": False,
        "release_gate_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CyberDetectionAssuranceFinding.model_validate(_sealed(draft))


def verify_cyber_detection_assurance_finding(
    *,
    finding: CyberDetectionAssuranceFinding,
) -> None:
    CyberDetectionAssuranceFinding.model_validate(finding.model_dump(mode="json"))


def _gap_severity(urgency: GlobalDefensiveUrgency) -> SecurityFindingSeverity:
    if urgency is GlobalDefensiveUrgency.CRITICAL:
        return SecurityFindingSeverity.CRITICAL
    if urgency is GlobalDefensiveUrgency.HIGH:
        return SecurityFindingSeverity.HIGH
    if urgency is GlobalDefensiveUrgency.MEDIUM:
        return SecurityFindingSeverity.MEDIUM
    return SecurityFindingSeverity.LOW


def _unverified_severity(urgency: GlobalDefensiveUrgency) -> SecurityFindingSeverity:
    if urgency in {GlobalDefensiveUrgency.CRITICAL, GlobalDefensiveUrgency.HIGH}:
        return SecurityFindingSeverity.HIGH
    if urgency is GlobalDefensiveUrgency.MEDIUM:
        return SecurityFindingSeverity.MEDIUM
    return SecurityFindingSeverity.LOW


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
