"""Evidence-bound defensive response candidates for EAY Jarvis.

Jarvis may recommend what security operators should verify, mitigate or contain,
but this layer never executes a defensive mutation and never creates a second
authorization system. The canonical mission/approval runtime remains the only owner
of execution authority.

V1 deliberately distinguishes three kinds of truth:
- current global threat context may guide defensive reasoning;
- exact company exposure decides whether mitigation may be proposed;
- confirmed linked company incident decides whether containment may be proposed.

Unknown/potential exposure permits verification only. Confirmed exposure permits
human-reviewed mitigation candidates. Confirmed linked incident permits
human-reviewed containment candidates. ATT&CK-derived detection recommendations are
allowed only when the exact current-threat receipt says the ATT&CK context is current.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.company_detection_coverage_intelligence import (
    CompanyDetectionCoverageReceipt,
    CompanyDetectionCoverageStatus,
)
from app.cyber_current_threat_context_intelligence import CurrentThreatContextReceipt
from app.cyber_defense_priority_intelligence import (
    CompanyExposureClaim,
    CompanyThreatDisposition,
    DefensivePriorityReceipt,
)

CYBER_DEFENSIVE_RESPONSE_CONTRACT = "eay-cyber-defensive-response-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class DefensiveResponseMode(str, Enum):
    MONITOR = "monitor"
    VERIFY = "verify"
    MITIGATE = "mitigate"
    CONTAIN = "contain"


class DefensiveResponseAction(str, Enum):
    MONITOR_THREAT = "monitor_threat"
    REFRESH_THREAT_CONTEXT = "refresh_threat_context"
    VERIFY_COMPANY_EXPOSURE = "verify_company_exposure"
    VERIFY_TELEMETRY_COVERAGE = "verify_telemetry_coverage"
    PREPARE_PATCH_OR_UPDATE = "prepare_patch_or_update"
    PREPARE_CONFIG_HARDENING = "prepare_config_hardening"
    PREPARE_DETECTION_RULE = "prepare_detection_rule"
    VERIFY_BACKUP_RESTORE_READINESS = "verify_backup_restore_readiness"
    PREPARE_ASSET_ISOLATION = "prepare_asset_isolation"
    PREPARE_SESSION_REVOCATION = "prepare_session_revocation"
    PREPARE_CREDENTIAL_ROTATION = "prepare_credential_rotation"


class DefensiveResponseMutationClass(str, Enum):
    READ_ONLY_VERIFICATION = "read_only_verification"
    MUTATING_DEFENSE_CANDIDATE = "mutating_defense_candidate"


_MUTATING_ACTIONS = {
    DefensiveResponseAction.PREPARE_PATCH_OR_UPDATE,
    DefensiveResponseAction.PREPARE_CONFIG_HARDENING,
    DefensiveResponseAction.PREPARE_DETECTION_RULE,
    DefensiveResponseAction.PREPARE_ASSET_ISOLATION,
    DefensiveResponseAction.PREPARE_SESSION_REVOCATION,
    DefensiveResponseAction.PREPARE_CREDENTIAL_ROTATION,
}

_CONTAINMENT_ACTIONS = {
    DefensiveResponseAction.PREPARE_ASSET_ISOLATION,
    DefensiveResponseAction.PREPARE_SESSION_REVOCATION,
    DefensiveResponseAction.PREPARE_CREDENTIAL_ROTATION,
}


class DefensiveResponseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSIVE_RESPONSE_CONTRACT
    candidate_id: str = Field(min_length=1)
    action: DefensiveResponseAction
    mutation_class: DefensiveResponseMutationClass
    rationale_codes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    human_review_required: bool
    canonical_execution_path_required: bool
    exploit_content_permitted: bool = False
    automatic_execution_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def candidate_is_advisory_and_authority_safe(self) -> DefensiveResponseCandidate:
        mutating = self.action in _MUTATING_ACTIONS
        expected_class = (
            DefensiveResponseMutationClass.MUTATING_DEFENSE_CANDIDATE
            if mutating
            else DefensiveResponseMutationClass.READ_ONLY_VERIFICATION
        )
        if self.mutation_class is not expected_class:
            raise ValueError("cyber_response_mutation_class_mismatch")
        if mutating and not self.human_review_required:
            raise ValueError("cyber_response_mutating_candidate_requires_human_review")
        if mutating and not self.canonical_execution_path_required:
            raise ValueError("cyber_response_mutating_candidate_requires_canonical_execution")
        if self.exploit_content_permitted:
            raise ValueError("cyber_response_exploit_content_forbidden")
        if self.automatic_execution_permitted:
            raise ValueError("cyber_response_automatic_execution_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_response_never_grants_execution_authority")
        _unique(self.rationale_codes, "cyber_response_rationale_codes_must_be_unique")
        _unique(self.evidence_refs, "cyber_response_evidence_refs_must_be_unique")
        for ref in (self.candidate_id, *self.rationale_codes, *self.evidence_refs):
            _safe_ref(ref, "cyber_response_unsafe_reference_forbidden")
        _verify(self, "cyber_response_candidate_fingerprint_mismatch")
        return self


class DefensiveResponsePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSIVE_RESPONSE_CONTRACT
    plan_id: str = Field(min_length=1)
    identity: CompanyIdentity
    priority_receipt_id: str = Field(min_length=1)
    priority_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_threat_context_id: str | None = None
    current_threat_context_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    detection_coverage_receipt_id: str | None = None
    detection_coverage_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    mode: DefensiveResponseMode
    candidates: tuple[DefensiveResponseCandidate, ...] = Field(min_length=1)
    firm_company_exposure_required_for_mutation: bool = True
    firm_company_incident_required_for_containment: bool = True
    human_review_required_before_mutation: bool = True
    automatic_execution_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def plan_preserves_truth_and_execution_boundaries(self) -> DefensiveResponsePlan:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if not self.firm_company_exposure_required_for_mutation:
            raise ValueError("cyber_response_mutation_requires_firm_company_exposure")
        if not self.firm_company_incident_required_for_containment:
            raise ValueError("cyber_response_containment_requires_firm_company_incident")
        if not self.human_review_required_before_mutation:
            raise ValueError("cyber_response_mutation_requires_human_review")
        if self.automatic_execution_permitted:
            raise ValueError("cyber_response_plan_automatic_execution_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_response_plan_never_grants_execution_authority")
        actions = tuple(item.action for item in self.candidates)
        _unique(
            tuple(item.value for item in actions),
            "cyber_response_plan_actions_must_be_unique",
        )
        if self.mode is DefensiveResponseMode.VERIFY and any(
            action in _MUTATING_ACTIONS for action in actions
        ):
            raise ValueError("cyber_response_verify_mode_cannot_contain_mutating_candidate")
        if self.mode is not DefensiveResponseMode.CONTAIN and any(
            action in _CONTAINMENT_ACTIONS for action in actions
        ):
            raise ValueError("cyber_response_containment_action_requires_contain_mode")
        for candidate in self.candidates:
            DefensiveResponseCandidate.model_validate(candidate.model_dump(mode="json"))
        for ref in (
            self.plan_id,
            self.priority_receipt_id,
            self.current_threat_context_id,
            self.detection_coverage_receipt_id,
        ):
            if ref is not None:
                _safe_ref(ref, "cyber_response_plan_unsafe_reference_forbidden")
        _verify(self, "cyber_response_plan_fingerprint_mismatch")
        return self


def build_defensive_response_plan(
    *,
    identity: CompanyIdentity,
    priority: DefensivePriorityReceipt,
    current_threat_context: CurrentThreatContextReceipt | None = None,
    detection_coverage: CompanyDetectionCoverageReceipt | None = None,
) -> DefensiveResponsePlan:
    """Compile evidence into response candidates without executing any mutation."""

    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    priority = DefensivePriorityReceipt.model_validate(priority.model_dump(mode="json"))
    if priority.identity.fingerprint != identity.fingerprint:
        raise ValueError("cyber_response_priority_company_mismatch")

    current_context: CurrentThreatContextReceipt | None = None
    detection: CompanyDetectionCoverageReceipt | None = None
    if current_threat_context is not None:
        current_context = CurrentThreatContextReceipt.model_validate(
            current_threat_context.model_dump(mode="json")
        )
    if detection_coverage is not None:
        detection = CompanyDetectionCoverageReceipt.model_validate(
            detection_coverage.model_dump(mode="json")
        )
        if detection.identity.fingerprint != identity.fingerprint:
            raise ValueError("cyber_response_detection_company_mismatch")
        if current_context is None:
            raise ValueError("cyber_response_detection_requires_current_threat_context")
        if (
            detection.global_enrichment_fingerprint
            != current_context.global_enrichment_fingerprint
        ):
            raise ValueError("cyber_response_detection_global_context_mismatch")

    actions: list[tuple[DefensiveResponseAction, tuple[str, ...], tuple[str, ...]]] = []
    priority_ref = f"cyber-priority:{priority.receipt_id}"

    if priority.exposure_claim in {
        CompanyExposureClaim.UNRESOLVED,
        CompanyExposureClaim.POSSIBLY_AFFECTED,
    }:
        mode = DefensiveResponseMode.VERIFY
        actions.append(
            (
                DefensiveResponseAction.VERIFY_COMPANY_EXPOSURE,
                ("company_exposure_not_firmly_resolved",),
                (priority_ref,),
            )
        )
        if current_context is not None and not current_context.current_global_reasoning_allowed:
            actions.append(
                (
                    DefensiveResponseAction.REFRESH_THREAT_CONTEXT,
                    ("global_attack_context_not_current",),
                    (f"current-threat-context:{current_context.context_id}",),
                )
            )
        if detection is not None and detection.coverage_status is CompanyDetectionCoverageStatus.UNVERIFIED:
            actions.append(
                (
                    DefensiveResponseAction.VERIFY_TELEMETRY_COVERAGE,
                    ("company_detection_coverage_unverified",),
                    (f"company-detection-coverage:{detection.receipt_id}",),
                )
            )
    elif priority.exposure_claim is CompanyExposureClaim.NOT_AFFECTED:
        mode = DefensiveResponseMode.MONITOR
        actions.append(
            (
                DefensiveResponseAction.MONITOR_THREAT,
                ("current_company_evidence_not_affected",),
                (priority_ref,),
            )
        )
    else:
        if not priority.firm_company_exposure_claim_authorized:
            raise ValueError("cyber_response_affected_claim_requires_firm_exposure")
        if priority.disposition is CompanyThreatDisposition.URGENT_INCIDENT_RESPONSE:
            if not priority.firm_company_incident_claim_authorized:
                raise ValueError("cyber_response_containment_requires_confirmed_incident")
            mode = DefensiveResponseMode.CONTAIN
            actions.extend(
                [
                    (
                        DefensiveResponseAction.PREPARE_ASSET_ISOLATION,
                        ("confirmed_exposure_and_linked_confirmed_incident",),
                        (priority_ref,),
                    ),
                    (
                        DefensiveResponseAction.PREPARE_SESSION_REVOCATION,
                        ("confirmed_incident_identity_containment_candidate",),
                        (priority_ref,),
                    ),
                    (
                        DefensiveResponseAction.PREPARE_CREDENTIAL_ROTATION,
                        ("confirmed_incident_credential_containment_candidate",),
                        (priority_ref,),
                    ),
                ]
            )
        else:
            mode = DefensiveResponseMode.MITIGATE

        actions.extend(
            [
                (
                    DefensiveResponseAction.PREPARE_PATCH_OR_UPDATE,
                    ("firm_company_exposure_confirmed",),
                    (priority_ref,),
                ),
                (
                    DefensiveResponseAction.PREPARE_CONFIG_HARDENING,
                    ("firm_company_exposure_confirmed",),
                    (priority_ref,),
                ),
                (
                    DefensiveResponseAction.VERIFY_BACKUP_RESTORE_READINESS,
                    ("defensive_recovery_readiness",),
                    (priority_ref,),
                ),
            ]
        )

        if detection is not None:
            detection_ref = f"company-detection-coverage:{detection.receipt_id}"
            if detection.coverage_status is CompanyDetectionCoverageStatus.UNVERIFIED:
                actions.append(
                    (
                        DefensiveResponseAction.VERIFY_TELEMETRY_COVERAGE,
                        ("company_detection_coverage_unverified",),
                        (detection_ref,),
                    )
                )
            elif detection.coverage_status is CompanyDetectionCoverageStatus.PARTIAL:
                if current_context is not None and current_context.current_global_reasoning_allowed:
                    actions.append(
                        (
                            DefensiveResponseAction.PREPARE_DETECTION_RULE,
                            ("confirmed_company_detection_gap_with_current_attack_context",),
                            (
                                detection_ref,
                                f"current-threat-context:{current_context.context_id}",
                            ),
                        )
                    )
                else:
                    actions.append(
                        (
                            DefensiveResponseAction.REFRESH_THREAT_CONTEXT,
                            ("detection_gap_present_but_attack_context_not_current",),
                            (detection_ref,),
                        )
                    )

    candidates = tuple(
        _candidate(action=action, rationale_codes=reasons, evidence_refs=evidence)
        for action, reasons, evidence in actions
    )
    plan_seed = {
        "identity": identity.fingerprint,
        "priority": priority.fingerprint,
        "current_context": current_context.fingerprint if current_context else None,
        "detection": detection.fingerprint if detection else None,
        "candidate_fingerprints": [item.fingerprint for item in candidates],
    }
    plan_id = f"cyber-response-plan:{_fingerprint(plan_seed)[:24]}"
    draft = {
        "contract": CYBER_DEFENSIVE_RESPONSE_CONTRACT,
        "plan_id": plan_id,
        "identity": identity.model_dump(mode="json"),
        "priority_receipt_id": priority.receipt_id,
        "priority_fingerprint": priority.fingerprint,
        "current_threat_context_id": current_context.context_id if current_context else None,
        "current_threat_context_fingerprint": (
            current_context.fingerprint if current_context else None
        ),
        "detection_coverage_receipt_id": detection.receipt_id if detection else None,
        "detection_coverage_fingerprint": detection.fingerprint if detection else None,
        "mode": mode.value,
        "candidates": [item.model_dump(mode="json") for item in candidates],
        "firm_company_exposure_required_for_mutation": True,
        "firm_company_incident_required_for_containment": True,
        "human_review_required_before_mutation": True,
        "automatic_execution_permitted": False,
        "execution_authority_granted": False,
    }
    return DefensiveResponsePlan.model_validate(_sealed(draft))


def verify_defensive_response_plan(*, plan: DefensiveResponsePlan) -> None:
    DefensiveResponsePlan.model_validate(plan.model_dump(mode="json"))


def _candidate(
    *,
    action: DefensiveResponseAction,
    rationale_codes: tuple[str, ...],
    evidence_refs: tuple[str, ...],
) -> DefensiveResponseCandidate:
    mutating = action in _MUTATING_ACTIONS
    seed = {
        "action": action.value,
        "rationale_codes": list(rationale_codes),
        "evidence_refs": list(evidence_refs),
    }
    candidate_id = f"cyber-response-candidate:{_fingerprint(seed)[:24]}"
    draft = {
        "contract": CYBER_DEFENSIVE_RESPONSE_CONTRACT,
        "candidate_id": candidate_id,
        "action": action.value,
        "mutation_class": (
            DefensiveResponseMutationClass.MUTATING_DEFENSE_CANDIDATE.value
            if mutating
            else DefensiveResponseMutationClass.READ_ONLY_VERIFICATION.value
        ),
        "rationale_codes": list(rationale_codes),
        "evidence_refs": list(evidence_refs),
        "human_review_required": mutating,
        "canonical_execution_path_required": mutating,
        "exploit_content_permitted": False,
        "automatic_execution_permitted": False,
        "execution_authority_granted": False,
    }
    return DefensiveResponseCandidate.model_validate(_sealed(draft))


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
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
