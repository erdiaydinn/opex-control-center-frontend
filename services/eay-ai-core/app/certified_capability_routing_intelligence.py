"""Fresh Frontier-3 engine admission for production routing.

Portfolio certification and benchmark integrity remain the source authorities.
This module only derives a short-lived, exact engine/model/provider/domain
admission lease. The lease can REMOVE routing candidates; it cannot grant spend,
Company Truth, provider authority, training, policy/model mutation or side effects.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .engine_gateway import RegisteredEngine
from .frontier3_certification_intelligence import (
    BenchmarkScenarioCoverage,
    Frontier3CertificationArtifact,
    Frontier3MatrixDisposition,
    FrontierCertificationDomain,
    FrontierCertificationStatus,
)
from .frontier_benchmark_integrity_intelligence import (
    FrontierBenchmarkIntegrityArtifact,
    FrontierBenchmarkValidity,
)
from .intelligence_router import IntelligenceTask

CERTIFIED_CAPABILITY_ROUTING_CONTRACT = "eay-certified-capability-routing-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _seal(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _payload(item: BaseModel) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={"fingerprint"})


_SealedT = TypeVar("_SealedT", bound=BaseModel)


def _fingerprint_for(model_type: type[_SealedT], values: dict[str, object]) -> str:
    """Seal the exact payload Pydantic will later validate.

    Constructors may omit fields that have model defaults and may pass Enum,
    datetime or nested-model instances. Sealing the raw constructor dictionary
    therefore produces a different digest from ``model_dump(mode='json')`` and
    makes a freshly created artifact fail its own integrity validator. Building a
    validation-free probe first applies model defaults and canonical JSON
    serialization without weakening final validation.
    """

    probe = model_type.model_construct(**values, fingerprint="0" * 64)
    return _seal(_payload(probe))


class AdmissionStatus(str, Enum):
    ADMITTED = "admitted"
    HOLD = "hold"
    BELOW_FRONTIER = "below_frontier"
    REVOKED = "revoked"


class AdmissionDisposition(str, Enum):
    READY = "ready"
    HOLD = "hold"
    REVOKED = "revoked"


class EngineCapabilityEvidence(SealedModel):
    evidence_id: str = Field(pattern=_SCOPE)
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    domain: FrontierCertificationDomain
    engine_id: str = Field(pattern=_SCOPE)
    model_id: str = Field(pattern=_SCOPE)
    provider_family: str = Field(pattern=_SCOPE)
    normalized_score: float = Field(ge=0, le=1)
    confidence_level: float = Field(default=.95, ge=.90, le=.999)
    sample_count: int = Field(ge=1)
    measured_at: datetime
    scenario_coverage: BenchmarkScenarioCoverage
    independent_evaluator_refs: tuple[str, ...] = Field(min_length=2)
    exact_adapter_verified: bool
    critical_safety_regression: bool = False
    contamination_detected: bool = False
    prompt_answer_leakage_detected: bool = False
    source_certification_fingerprint: str = Field(pattern=_DIGEST)
    source_integrity_fingerprint: str = Field(pattern=_DIGEST)
    evidence_refs: tuple[str, ...] = Field(min_length=2)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral(self) -> "EngineCapabilityEvidence":
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("capability_evidence_requires_timezone")
        if len(set(self.independent_evaluator_refs)) != len(
            self.independent_evaluator_refs
        ):
            raise ValueError("capability_evaluators_must_be_unique")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("capability_evidence_refs_must_be_unique")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("capability_evidence_fingerprint_mismatch")
        return self


class CertifiedCapabilityPolicy(SealedModel):
    minimum_sample_count: int = Field(default=100, ge=20)
    minimum_confidence_level: float = Field(default=.95, ge=.90, le=.999)
    maximum_measurement_age_days: int = Field(default=30, ge=1, le=180)
    maximum_integrity_age_hours: int = Field(default=24, ge=1, le=168)
    minimum_evaluators: int = Field(default=2, ge=2, le=8)
    minimum_frontier_ratio: float = Field(default=1.0, ge=1.0, le=1.2)
    require_complete_scenarios: bool = True

    @model_validator(mode="after")
    def strict(self) -> "CertifiedCapabilityPolicy":
        if not self.require_complete_scenarios:
            raise ValueError("capability_complete_scenarios_cannot_be_disabled")
        return self


class EngineAdmission(SealedModel):
    engine_id: str = Field(pattern=_SCOPE)
    model_id: str = Field(pattern=_SCOPE)
    provider_family: str = Field(pattern=_SCOPE)
    domain: FrontierCertificationDomain
    status: AdmissionStatus
    normalized_score: float = Field(ge=0, le=1)
    strongest_frontier_score: float = Field(ge=0, le=1)
    valid_until: datetime
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral(self) -> "EngineAdmission":
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("engine_admission_requires_timezone")
        if (self.status is AdmissionStatus.ADMITTED) == bool(self.blockers):
            raise ValueError("engine_admission_status_blocker_mismatch")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("engine_admission_fingerprint_mismatch")
        return self


class CertifiedCapabilitySnapshot(SealedModel):
    contract: str = CERTIFIED_CAPABILITY_ROUTING_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    jarvis_system_version: str = Field(pattern=_SCOPE)
    checked_at: datetime
    valid_until: datetime
    source_certification_fingerprint: str = Field(pattern=_DIGEST)
    source_integrity_fingerprint: str = Field(pattern=_DIGEST)
    admissions: tuple[EngineAdmission, ...]
    disposition: AdmissionDisposition
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provider_authority_granted: bool = False
    company_truth_promoted: bool = False
    paid_token_authority_granted: bool = False
    automatic_training_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral(self) -> "CertifiedCapabilitySnapshot":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("capability_snapshot_requires_timezone")
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("capability_snapshot_valid_until_requires_timezone")
        if self.disposition is AdmissionDisposition.READY:
            if self.blockers or self.valid_until <= self.checked_at:
                raise ValueError("capability_ready_snapshot_invalid")
            if not any(
                x.status is AdmissionStatus.ADMITTED for x in self.admissions
            ):
                raise ValueError("capability_ready_snapshot_requires_admission")
        elif not self.blockers:
            raise ValueError("capability_nonready_snapshot_requires_blocker")
        if any(
            (
                self.provider_authority_granted,
                self.company_truth_promoted,
                self.paid_token_authority_granted,
                self.automatic_training_allowed,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("capability_snapshot_never_mints_authority")
        keys = [(x.engine_id, x.domain) for x in self.admissions]
        if len(keys) != len(set(keys)):
            raise ValueError("capability_snapshot_duplicate_engine_domain")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("capability_snapshot_fingerprint_mismatch")
        return self


def seal_engine_capability_evidence(**values: object) -> EngineCapabilityEvidence:
    payload = dict(values)
    payload["fingerprint"] = _fingerprint_for(
        EngineCapabilityEvidence, payload
    )
    return EngineCapabilityEvidence.model_validate(payload)


def _domain(
    source: Frontier3CertificationArtifact,
    domain: FrontierCertificationDomain,
):
    rows = [x for x in source.domain_certifications if x.domain is domain]
    if len(rows) != 1:
        raise ValueError("capability_source_domain_not_unique")
    return rows[0]


def _admission(**values: object) -> EngineAdmission:
    payload = dict(values)
    payload["fingerprint"] = _fingerprint_for(EngineAdmission, payload)
    return EngineAdmission.model_validate(payload)


def build_certified_capability_snapshot(
    *,
    source: Frontier3CertificationArtifact,
    integrity: FrontierBenchmarkIntegrityArtifact,
    checked_at: datetime,
    engine_evidence: tuple[EngineCapabilityEvidence, ...],
    policy: CertifiedCapabilityPolicy | None = None,
) -> CertifiedCapabilitySnapshot:
    source = Frontier3CertificationArtifact.model_validate(
        source.model_dump(mode="json")
    )
    integrity = FrontierBenchmarkIntegrityArtifact.model_validate(
        integrity.model_dump(mode="json")
    )
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("capability_snapshot_check_requires_timezone")
    if integrity.tenant_id != source.tenant_id or integrity.company_id != source.company_id:
        raise ValueError("capability_snapshot_scope_mismatch")
    if integrity.source_certification_fingerprint != source.fingerprint:
        raise ValueError("capability_snapshot_integrity_source_mismatch")
    if integrity.current_jarvis_system_version != source.jarvis_system_version:
        raise ValueError("capability_snapshot_jarvis_version_mismatch")
    rules = policy or CertifiedCapabilityPolicy()
    blockers: list[str] = []
    disposition = AdmissionDisposition.READY
    if source.disposition is not Frontier3MatrixDisposition.CERTIFIED:
        blockers.append("source_matrix_not_certified")
        disposition = AdmissionDisposition.HOLD
    if integrity.validity is FrontierBenchmarkValidity.REVOKED:
        blockers.append("benchmark_integrity_revoked")
        disposition = AdmissionDisposition.REVOKED
    elif integrity.validity is not FrontierBenchmarkValidity.VALID:
        blockers.append("benchmark_integrity_not_valid")
        disposition = AdmissionDisposition.HOLD
    integrity_until = integrity.checked_at + timedelta(
        hours=rules.maximum_integrity_age_hours
    )
    if checked_at > integrity_until:
        blockers.append("benchmark_integrity_stale")
        if disposition is AdmissionDisposition.READY:
            disposition = AdmissionDisposition.HOLD
    ids = [x.evidence_id for x in engine_evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("capability_evidence_ids_must_be_unique")

    admissions: list[EngineAdmission] = []
    refs = set(source.evidence_refs) | set(integrity.evidence_refs)
    for raw in engine_evidence:
        item = EngineCapabilityEvidence.model_validate(raw.model_dump(mode="json"))
        if item.tenant_id != source.tenant_id or item.company_id != source.company_id:
            raise ValueError("capability_evidence_cross_scope_forbidden")
        if item.source_certification_fingerprint != source.fingerprint:
            raise ValueError("capability_evidence_certificate_mismatch")
        if item.source_integrity_fingerprint != integrity.fingerprint:
            raise ValueError("capability_evidence_integrity_mismatch")
        row = _domain(source, item.domain)
        status = AdmissionStatus.ADMITTED
        reasons: list[str] = []
        item_until = item.measured_at + timedelta(
            days=rules.maximum_measurement_age_days
        )
        checks = (
            (item.measured_at > checked_at, "future_measurement"),
            (checked_at > item_until, "measurement_stale"),
            (
                item.sample_count < rules.minimum_sample_count,
                "sample_count_insufficient",
            ),
            (
                item.confidence_level < rules.minimum_confidence_level,
                "confidence_insufficient",
            ),
            (
                rules.require_complete_scenarios
                and not item.scenario_coverage.complete,
                "scenario_coverage_incomplete",
            ),
            (
                len(item.independent_evaluator_refs) < rules.minimum_evaluators,
                "evaluator_quorum_missing",
            ),
            (not item.exact_adapter_verified, "exact_adapter_not_verified"),
        )
        for failed, reason in checks:
            if failed:
                reasons.append(reason)
                status = AdmissionStatus.HOLD
        if (
            item.critical_safety_regression
            or item.contamination_detected
            or item.prompt_answer_leakage_detected
        ):
            reasons.append("safety_or_contamination_revocation")
            status = AdmissionStatus.REVOKED
        if row.status not in {
            FrontierCertificationStatus.FRONTIER_PARITY,
            FrontierCertificationStatus.STATISTICALLY_SUPERIOR,
        }:
            reasons.append("source_domain_not_frontier_parity")
            if status is AdmissionStatus.ADMITTED:
                status = AdmissionStatus.HOLD
        floor = min(
            1.0,
            row.strongest_frontier_score * rules.minimum_frontier_ratio,
        )
        if item.normalized_score < floor:
            reasons.append("engine_below_strongest_frontier")
            if status is AdmissionStatus.ADMITTED:
                status = AdmissionStatus.BELOW_FRONTIER
        if disposition is AdmissionDisposition.REVOKED:
            reasons.append("global_integrity_revoked")
            status = AdmissionStatus.REVOKED
        elif (
            disposition is not AdmissionDisposition.READY
            and status is AdmissionStatus.ADMITTED
        ):
            reasons.append("global_integrity_hold")
            status = AdmissionStatus.HOLD
        item_refs = tuple(
            dict.fromkeys(
                (
                    *item.evidence_refs,
                    f"frontier3-cert://{source.fingerprint}",
                    f"frontier-integrity://{integrity.fingerprint}",
                )
            )
        )
        refs.update(item_refs)
        admissions.append(
            _admission(
                engine_id=item.engine_id,
                model_id=item.model_id,
                provider_family=item.provider_family,
                domain=item.domain,
                status=status,
                normalized_score=item.normalized_score,
                strongest_frontier_score=row.strongest_frontier_score,
                valid_until=min(integrity_until, item_until),
                blockers=tuple(dict.fromkeys(reasons)),
                evidence_refs=item_refs,
            )
        )

    admitted = [
        x for x in admissions if x.status is AdmissionStatus.ADMITTED
    ]
    if disposition is AdmissionDisposition.READY and not admitted:
        blockers.append("no_engine_meets_frontier_floor")
        disposition = AdmissionDisposition.HOLD
    valid_until = min(
        (x.valid_until for x in admitted),
        default=integrity_until,
    )
    payload: dict[str, object] = dict(
        tenant_id=source.tenant_id,
        company_id=source.company_id,
        jarvis_system_version=source.jarvis_system_version,
        checked_at=checked_at,
        valid_until=valid_until,
        source_certification_fingerprint=source.fingerprint,
        source_integrity_fingerprint=integrity.fingerprint,
        admissions=tuple(admissions),
        disposition=disposition,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_refs=tuple(sorted(refs)),
    )
    payload["fingerprint"] = _fingerprint_for(
        CertifiedCapabilitySnapshot, payload
    )
    return CertifiedCapabilitySnapshot.model_validate(payload)


@dataclass(frozen=True)
class CertifiedEngineCandidateAdmission:
    snapshot: CertifiedCapabilitySnapshot

    def receipt_ref(
        self,
        *,
        task: IntelligenceTask,
        requested_at: datetime,
        tenant_ref: str,
        company_ref: str | None,
    ) -> str | None:
        if not task.requires_fresh_certification:
            return None
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            return None
        if (
            tenant_ref != self.snapshot.tenant_id
            or company_ref != self.snapshot.company_id
        ):
            return None
        if self.snapshot.disposition is not AdmissionDisposition.READY:
            return None
        if not self.snapshot.checked_at <= requested_at <= self.snapshot.valid_until:
            return None
        return f"capability-cert://{self.snapshot.fingerprint}"

    def is_admitted(
        self,
        *,
        task: IntelligenceTask,
        registration: RegisteredEngine,
        requested_at: datetime,
        tenant_ref: str,
        company_ref: str | None,
    ) -> bool:
        if not task.requires_fresh_certification:
            return True
        if (
            task.certification_domain is None
            or self.receipt_ref(
                task=task,
                requested_at=requested_at,
                tenant_ref=tenant_ref,
                company_ref=company_ref,
            )
            is None
        ):
            return False
        matches = [
            x
            for x in self.snapshot.admissions
            if x.status is AdmissionStatus.ADMITTED
            and x.domain is task.certification_domain
            and x.engine_id == registration.profile.engine_id
            and x.model_id == registration.endpoint.model_id
            and x.provider_family
            == registration.profile.independent_provider_key
            and requested_at <= x.valid_until
        ]
        return len(matches) == 1
