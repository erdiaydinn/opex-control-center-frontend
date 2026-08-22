"""Company-bound detection coverage for global ATT&CK defensive context.

Global ATT&CK detection/data-component knowledge is tenant-neutral. Whether a
specific company actually collects the required telemetry is company truth and
must be proven separately. This contract joins those planes without treating
absence of an observation as proof that telemetry is missing.

V1 invariants:
- every company capability observation is exact-tenant/company bound;
- AVAILABLE, DEGRADED and MISSING states all require company evidence;
- absent or stale company evidence becomes UNVERIFIED, never MISSING;
- a firm coverage/gap claim is allowed only when every required data component has
  current company evidence;
- no detection deployment, remediation or execution authority is granted.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.cyber_threat_enrichment_intelligence import GlobalThreatEnrichmentReceipt

COMPANY_DETECTION_COVERAGE_CONTRACT = "eay-company-detection-coverage-v1"

_DATA_COMPONENT_ID = re.compile(r"^DC\d{4}$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class CompanyTelemetryCapabilityStatus(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    MISSING = "missing"


class CompanyDetectionCoverageStatus(str, Enum):
    NO_GLOBAL_REQUIREMENTS = "no_global_requirements"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    COVERED = "covered"


class CompanyTelemetryCapabilityObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = COMPANY_DETECTION_COVERAGE_CONTRACT
    observation_id: str = Field(min_length=1)
    identity: CompanyIdentity
    data_component_id: str
    status: CompanyTelemetryCapabilityStatus
    telemetry_ref: str | None = None
    detection_rule_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    firm_company_telemetry_claim_authorized: bool = True
    deployment_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_company_bound_and_evidenced(
        self,
    ) -> CompanyTelemetryCapabilityObservation:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if not _DATA_COMPONENT_ID.fullmatch(self.data_component_id):
            raise ValueError("company_detection_invalid_data_component_id")
        _aware(self.observed_at, "company_detection_observed_at_requires_timezone")
        _aware(self.recorded_at, "company_detection_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("company_detection_recorded_at_predates_observation")
        if self.status in {
            CompanyTelemetryCapabilityStatus.AVAILABLE,
            CompanyTelemetryCapabilityStatus.DEGRADED,
        } and self.telemetry_ref is None:
            raise ValueError("company_detection_available_or_degraded_requires_telemetry_ref")
        if (
            self.status is CompanyTelemetryCapabilityStatus.MISSING
            and (self.telemetry_ref is not None or self.detection_rule_refs)
        ):
            raise ValueError("company_detection_missing_cannot_claim_live_telemetry")
        if not self.firm_company_telemetry_claim_authorized:
            raise ValueError("company_detection_observation_must_be_evidence_claim")
        if self.deployment_authority_granted:
            raise ValueError("company_detection_observation_never_grants_deployment_authority")
        if self.execution_authority_granted:
            raise ValueError("company_detection_observation_never_grants_execution_authority")
        _unique(self.detection_rule_refs, "company_detection_rule_refs_must_be_unique")
        _unique(self.evidence_refs, "company_detection_evidence_refs_must_be_unique")
        for ref in (
            self.observation_id,
            self.telemetry_ref,
            *self.detection_rule_refs,
            *self.evidence_refs,
        ):
            if ref is not None:
                _safe_ref(ref, "company_detection_unsafe_reference_forbidden")
        _verify(self, "company_detection_observation_fingerprint_mismatch")
        return self


class CompanyDetectionCoverageReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = COMPANY_DETECTION_COVERAGE_CONTRACT
    receipt_id: str = Field(min_length=1)
    identity: CompanyIdentity
    as_of: datetime
    max_company_evidence_age_seconds: int = Field(gt=0)
    global_enrichment_receipt_id: str = Field(min_length=1)
    global_enrichment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    cve_id: str
    required_data_component_ids: tuple[str, ...]
    current_observed_component_ids: tuple[str, ...]
    available_component_ids: tuple[str, ...]
    degraded_component_ids: tuple[str, ...]
    missing_component_ids: tuple[str, ...]
    unverified_component_ids: tuple[str, ...]
    coverage_status: CompanyDetectionCoverageStatus
    verified_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    firm_company_detection_claim_authorized: bool = False
    reason_codes: tuple[str, ...] = Field(min_length=1)
    remediation_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_does_not_turn_unknown_into_gap(self) -> CompanyDetectionCoverageReceipt:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.as_of, "company_detection_receipt_as_of_requires_timezone")
        component_sets = {
            "required": set(self.required_data_component_ids),
            "current": set(self.current_observed_component_ids),
            "available": set(self.available_component_ids),
            "degraded": set(self.degraded_component_ids),
            "missing": set(self.missing_component_ids),
            "unverified": set(self.unverified_component_ids),
        }
        for name, values in component_sets.items():
            if len(values) != len(getattr(self, f"{name}_data_component_ids", ())) and name == "required":
                raise ValueError("company_detection_required_components_must_be_unique")
        for values in (
            self.required_data_component_ids,
            self.current_observed_component_ids,
            self.available_component_ids,
            self.degraded_component_ids,
            self.missing_component_ids,
            self.unverified_component_ids,
        ):
            _unique(values, "company_detection_component_sets_must_be_unique")
            if any(not _DATA_COMPONENT_ID.fullmatch(value) for value in values):
                raise ValueError("company_detection_invalid_data_component_id")

        required = component_sets["required"]
        classified = (
            component_sets["available"]
            | component_sets["degraded"]
            | component_sets["missing"]
            | component_sets["unverified"]
        )
        if classified != required:
            raise ValueError("company_detection_component_classification_mismatch")
        if (
            component_sets["available"] & component_sets["degraded"]
            or component_sets["available"] & component_sets["missing"]
            or component_sets["available"] & component_sets["unverified"]
            or component_sets["degraded"] & component_sets["missing"]
            or component_sets["degraded"] & component_sets["unverified"]
            or component_sets["missing"] & component_sets["unverified"]
        ):
            raise ValueError("company_detection_component_classification_overlap")
        if component_sets["current"] != (
            component_sets["available"]
            | component_sets["degraded"]
            | component_sets["missing"]
        ):
            raise ValueError("company_detection_current_component_set_mismatch")

        if self.firm_company_detection_claim_authorized:
            if self.unverified_component_ids:
                raise ValueError("company_detection_firm_claim_requires_complete_current_evidence")
            if self.coverage_status not in {
                CompanyDetectionCoverageStatus.COVERED,
                CompanyDetectionCoverageStatus.PARTIAL,
            }:
                raise ValueError("company_detection_firm_claim_requires_resolved_coverage")
            if self.verified_coverage_ratio is None:
                raise ValueError("company_detection_firm_claim_requires_coverage_ratio")
        else:
            if self.coverage_status in {
                CompanyDetectionCoverageStatus.COVERED,
                CompanyDetectionCoverageStatus.PARTIAL,
            }:
                raise ValueError("company_detection_resolved_coverage_requires_firm_claim")
            if self.verified_coverage_ratio is not None:
                raise ValueError("company_detection_unverified_receipt_cannot_claim_ratio")
        if self.coverage_status is CompanyDetectionCoverageStatus.NO_GLOBAL_REQUIREMENTS:
            if required:
                raise ValueError("company_detection_no_requirements_requires_empty_required_set")
        elif not required:
            raise ValueError("company_detection_required_set_cannot_be_empty")

        if self.remediation_authority_granted:
            raise ValueError("company_detection_never_grants_remediation_authority")
        if self.execution_authority_granted:
            raise ValueError("company_detection_never_grants_execution_authority")
        _unique(self.reason_codes, "company_detection_reason_codes_must_be_unique")
        for ref in (self.receipt_id, self.global_enrichment_receipt_id, *self.reason_codes):
            _safe_ref(ref, "company_detection_receipt_unsafe_reference_forbidden")
        _verify(self, "company_detection_receipt_fingerprint_mismatch")
        return self


def build_company_telemetry_capability_observation(
    *,
    identity: CompanyIdentity,
    observation_id: str,
    data_component_id: str,
    status: CompanyTelemetryCapabilityStatus,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    telemetry_ref: str | None = None,
    detection_rule_refs: tuple[str, ...] = (),
) -> CompanyTelemetryCapabilityObservation:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": COMPANY_DETECTION_COVERAGE_CONTRACT,
        "observation_id": observation_id,
        "identity": identity.model_dump(mode="json"),
        "data_component_id": data_component_id,
        "status": status.value,
        "telemetry_ref": telemetry_ref,
        "detection_rule_refs": list(detection_rule_refs),
        "evidence_refs": list(evidence_refs),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "firm_company_telemetry_claim_authorized": True,
        "deployment_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyTelemetryCapabilityObservation.model_validate(_sealed(draft))


def assess_company_detection_coverage(
    *,
    identity: CompanyIdentity,
    global_enrichment: GlobalThreatEnrichmentReceipt,
    observations: tuple[CompanyTelemetryCapabilityObservation, ...],
    as_of: datetime,
    max_company_evidence_age_seconds: int,
) -> CompanyDetectionCoverageReceipt:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    global_enrichment = GlobalThreatEnrichmentReceipt.model_validate(
        global_enrichment.model_dump(mode="json")
    )
    _aware(as_of, "company_detection_receipt_as_of_requires_timezone")
    if max_company_evidence_age_seconds <= 0:
        raise ValueError("company_detection_max_evidence_age_must_be_positive")
    if global_enrichment.as_of > as_of:
        raise ValueError("company_detection_future_global_enrichment_forbidden")

    required = tuple(sorted(global_enrichment.data_component_ids))
    if not required:
        return _build_receipt(
            identity=identity,
            global_enrichment=global_enrichment,
            as_of=as_of,
            max_company_evidence_age_seconds=max_company_evidence_age_seconds,
            required=(),
            current=(),
            available=(),
            degraded=(),
            missing=(),
            unverified=(),
            status=CompanyDetectionCoverageStatus.NO_GLOBAL_REQUIREMENTS,
            ratio=None,
            firm=False,
            reasons=("global_enrichment_has_no_data_component_requirement",),
        )

    by_component: dict[str, CompanyTelemetryCapabilityObservation] = {}
    for raw in observations:
        observation = CompanyTelemetryCapabilityObservation.model_validate(
            raw.model_dump(mode="json")
        )
        if observation.identity.fingerprint != identity.fingerprint:
            raise ValueError("company_detection_cross_company_observation_forbidden")
        if observation.data_component_id not in required:
            raise ValueError("company_detection_observation_not_required_by_global_context")
        if observation.data_component_id in by_component:
            raise ValueError("company_detection_duplicate_component_observation")
        if observation.observed_at > as_of or observation.recorded_at > as_of:
            raise ValueError("company_detection_future_known_observation_forbidden")
        by_component[observation.data_component_id] = observation

    current_map: dict[str, CompanyTelemetryCapabilityObservation] = {}
    for component_id, observation in by_component.items():
        age_seconds = (as_of - observation.observed_at).total_seconds()
        if age_seconds <= max_company_evidence_age_seconds:
            current_map[component_id] = observation

    available = tuple(
        sorted(
            component_id
            for component_id, observation in current_map.items()
            if observation.status is CompanyTelemetryCapabilityStatus.AVAILABLE
        )
    )
    degraded = tuple(
        sorted(
            component_id
            for component_id, observation in current_map.items()
            if observation.status is CompanyTelemetryCapabilityStatus.DEGRADED
        )
    )
    missing = tuple(
        sorted(
            component_id
            for component_id, observation in current_map.items()
            if observation.status is CompanyTelemetryCapabilityStatus.MISSING
        )
    )
    current = tuple(sorted(current_map))
    unverified = tuple(sorted(set(required) - set(current)))

    if unverified:
        status = CompanyDetectionCoverageStatus.UNVERIFIED
        ratio = None
        firm = False
        reasons = ["company_detection_evidence_incomplete_or_stale"]
        if missing:
            reasons.append("current_evidence_confirms_some_detection_gaps")
    else:
        firm = True
        ratio = len(available) / len(required)
        if len(available) == len(required):
            status = CompanyDetectionCoverageStatus.COVERED
            reasons = ["all_required_data_components_current_and_available"]
        else:
            status = CompanyDetectionCoverageStatus.PARTIAL
            reasons = ["complete_current_evidence_confirms_detection_coverage_gap"]
            if degraded:
                reasons.append("degraded_detection_components_present")
            if missing:
                reasons.append("missing_detection_components_present")

    return _build_receipt(
        identity=identity,
        global_enrichment=global_enrichment,
        as_of=as_of,
        max_company_evidence_age_seconds=max_company_evidence_age_seconds,
        required=required,
        current=current,
        available=available,
        degraded=degraded,
        missing=missing,
        unverified=unverified,
        status=status,
        ratio=ratio,
        firm=firm,
        reasons=tuple(reasons),
    )


def verify_company_detection_coverage_receipt(
    *,
    receipt: CompanyDetectionCoverageReceipt,
) -> None:
    CompanyDetectionCoverageReceipt.model_validate(receipt.model_dump(mode="json"))


def _build_receipt(
    *,
    identity: CompanyIdentity,
    global_enrichment: GlobalThreatEnrichmentReceipt,
    as_of: datetime,
    max_company_evidence_age_seconds: int,
    required: tuple[str, ...],
    current: tuple[str, ...],
    available: tuple[str, ...],
    degraded: tuple[str, ...],
    missing: tuple[str, ...],
    unverified: tuple[str, ...],
    status: CompanyDetectionCoverageStatus,
    ratio: float | None,
    firm: bool,
    reasons: tuple[str, ...],
) -> CompanyDetectionCoverageReceipt:
    seed = {
        "identity": identity.fingerprint,
        "global_enrichment": global_enrichment.fingerprint,
        "as_of": _iso(as_of),
        "max_age": max_company_evidence_age_seconds,
        "required": list(required),
        "current": list(current),
        "available": list(available),
        "degraded": list(degraded),
        "missing": list(missing),
        "unverified": list(unverified),
    }
    receipt_id = f"company-detection-coverage:{_fingerprint(seed)[:24]}"
    draft = {
        "contract": COMPANY_DETECTION_COVERAGE_CONTRACT,
        "receipt_id": receipt_id,
        "identity": identity.model_dump(mode="json"),
        "as_of": _iso(as_of),
        "max_company_evidence_age_seconds": max_company_evidence_age_seconds,
        "global_enrichment_receipt_id": global_enrichment.receipt_id,
        "global_enrichment_fingerprint": global_enrichment.fingerprint,
        "cve_id": global_enrichment.cve_id,
        "required_data_component_ids": list(required),
        "current_observed_component_ids": list(current),
        "available_component_ids": list(available),
        "degraded_component_ids": list(degraded),
        "missing_component_ids": list(missing),
        "unverified_component_ids": list(unverified),
        "coverage_status": status.value,
        "verified_coverage_ratio": ratio,
        "firm_company_detection_claim_authorized": firm,
        "reason_codes": list(reasons),
        "remediation_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyDetectionCoverageReceipt.model_validate(_sealed(draft))


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "company_detection_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


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
