"""Benchmark-integrity and frontier-drift validity authority for Jarvis.

A Frontier-3 certificate is not permanently trustworthy just because it once passed.
This layer replays the exact certification against the supplied measurement set, then
checks hidden/rotated evaluation integrity, contamination/leakage audits, current
frontier model releases, Jarvis version drift, benchmark protocol rotation and
measurement ageing.

It can preserve or revoke a bounded benchmark claim. It never grants provider,
training, model/policy mutation, Company Truth, execution or side-effect authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frontier3_certification_intelligence import (
    BenchmarkProtocolIdentity,
    Frontier3CertificationArtifact,
    Frontier3CertificationPolicy,
    Frontier3MatrixDisposition,
    FrontierCertificationDomain,
    FrontierSystemMeasurement,
    JarvisDomainMeasurement,
    certify_frontier3_matrix,
)

FRONTIER_BENCHMARK_INTEGRITY_CONTRACT = "eay-frontier-benchmark-integrity-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BenchmarkExposureMode(str, Enum):
    SECRET_HOLDOUT = "secret_holdout"
    ROTATED_HOLDOUT = "rotated_holdout"
    PUBLIC_STATIC = "public_static"


class FrontierBenchmarkValidity(str, Enum):
    VALID = "valid"
    HOLD = "hold"
    REVOKED = "revoked"


class BenchmarkIntegrityPolicy(SealedModel):
    minimum_independent_auditors: int = Field(default=2, ge=2, le=8)
    minimum_unseen_item_fraction: float = Field(default=0.20, ge=0.05, le=1.0)
    maximum_public_overlap_fraction: float = Field(default=0.05, ge=0.0, le=0.25)
    require_hidden_or_rotated_eval: bool = True

    @model_validator(mode="after")
    def strict_hidden_eval(self) -> "BenchmarkIntegrityPolicy":
        if not self.require_hidden_or_rotated_eval:
            raise ValueError("frontier_integrity_hidden_or_rotated_eval_cannot_be_disabled")
        return self


class MeasurementIntegrityAudit(SealedModel):
    audit_id: str = Field(pattern=_SCOPE)
    measurement_id: str = Field(pattern=_SCOPE)
    auditor_ref: str = Field(pattern=_SCOPE)
    independent_auditor: bool
    audited_at: datetime
    exposure_mode: BenchmarkExposureMode
    rotation_id: str | None = Field(default=None, pattern=_SCOPE)
    unseen_item_fraction: float = Field(ge=0.0, le=1.0)
    known_public_overlap_fraction: float = Field(ge=0.0, le=1.0)
    prompt_answer_leakage_detected: bool
    contamination_detected: bool
    evidence_refs: tuple[str, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def audit_is_integral(self) -> "MeasurementIntegrityAudit":
        if self.audited_at.tzinfo is None or self.audited_at.utcoffset() is None:
            raise ValueError("frontier_integrity_audit_requires_timezone")
        if self.exposure_mode is BenchmarkExposureMode.ROTATED_HOLDOUT and not self.rotation_id:
            raise ValueError("frontier_integrity_rotated_holdout_requires_rotation_id")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("frontier_integrity_audit_evidence_refs_must_be_unique")
        return self


class CurrentFrontierRelease(SealedModel):
    provider_family: str = Field(pattern=_SCOPE)
    system_id: str = Field(pattern=_SCOPE)
    system_version: str = Field(pattern=_SCOPE)
    released_at: datetime
    benchmark_eligible: bool
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def release_requires_timezone(self) -> "CurrentFrontierRelease":
        if self.released_at.tzinfo is None or self.released_at.utcoffset() is None:
            raise ValueError("frontier_integrity_release_requires_timezone")
        return self


class CurrentBenchmarkProtocol(SealedModel):
    domain: FrontierCertificationDomain
    protocol: BenchmarkProtocolIdentity
    effective_at: datetime
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def protocol_requires_timezone(self) -> "CurrentBenchmarkProtocol":
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("frontier_integrity_protocol_requires_timezone")
        return self


class FrontierBenchmarkIntegrityArtifact(SealedModel):
    contract: str = FRONTIER_BENCHMARK_INTEGRITY_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    source_certification_fingerprint: str = Field(pattern=_DIGEST)
    source_certification_id: str = Field(pattern=_SCOPE)
    source_jarvis_system_version: str = Field(pattern=_SCOPE)
    current_jarvis_system_version: str = Field(pattern=_SCOPE)
    checked_at: datetime
    audited_measurement_count: int = Field(ge=0)
    frontier_release_count: int = Field(ge=0)
    current_protocol_count: int = Field(ge=0)
    validity: FrontierBenchmarkValidity
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    bounded_matrix_parity_claim_still_valid: bool
    bounded_matrix_superiority_claim_still_valid: bool
    universal_superiority_claim_allowed: bool = False
    company_truth_promoted: bool = False
    provider_authority_granted: bool = False
    automatic_training_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def artifact_is_integral_and_non_authoritative(self) -> "FrontierBenchmarkIntegrityArtifact":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("frontier_integrity_check_requires_timezone")
        if any(
            (
                self.universal_superiority_claim_allowed,
                self.company_truth_promoted,
                self.provider_authority_granted,
                self.automatic_training_allowed,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("frontier_integrity_never_mints_change_or_execution_authority")
        if self.validity is FrontierBenchmarkValidity.VALID:
            if self.blockers or not self.bounded_matrix_parity_claim_still_valid:
                raise ValueError("frontier_integrity_valid_requires_clean_bounded_claim")
        elif self.bounded_matrix_parity_claim_still_valid or self.bounded_matrix_superiority_claim_still_valid:
            raise ValueError("frontier_integrity_hold_or_revoked_cannot_keep_claim")
        if self.bounded_matrix_superiority_claim_still_valid and not self.bounded_matrix_parity_claim_still_valid:
            raise ValueError("frontier_integrity_superiority_requires_parity_validity")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("frontier_integrity_fingerprint_mismatch")
        return self


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload(item: BaseModel) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={"fingerprint"})


def _protocol_key(protocol: BenchmarkProtocolIdentity) -> tuple[str, ...]:
    return (
        protocol.protocol_id,
        protocol.protocol_version,
        protocol.task_set_id,
        protocol.task_set_fingerprint,
        protocol.environment_fingerprint,
        protocol.metric_set_fingerprint,
    )


def _replay_source_certification(
    *,
    source: Frontier3CertificationArtifact,
    jarvis_measurements: tuple[JarvisDomainMeasurement, ...],
    frontier_measurements: tuple[FrontierSystemMeasurement, ...],
    certification_policy: Frontier3CertificationPolicy,
) -> None:
    allowed_domains = set(source.required_domains)
    if any(item.domain not in allowed_domains for item in jarvis_measurements):
        raise ValueError("frontier_integrity_unscoped_jarvis_measurement_forbidden")
    if any(item.domain not in allowed_domains for item in frontier_measurements):
        raise ValueError("frontier_integrity_unscoped_frontier_measurement_forbidden")
    if tuple(certification_policy.required_domains) != tuple(source.required_domains):
        raise ValueError("frontier_integrity_policy_domain_scope_mismatch")

    replay = certify_frontier3_matrix(
        certification_id=source.certification_id,
        tenant_id=source.tenant_id,
        company_id=source.company_id,
        jarvis_system_id=source.jarvis_system_id,
        jarvis_system_version=source.jarvis_system_version,
        assessed_at=source.assessed_at,
        jarvis_measurements=jarvis_measurements,
        frontier_measurements=frontier_measurements,
        policy=certification_policy,
    )
    if replay.fingerprint != source.fingerprint:
        raise ValueError("frontier_integrity_recertification_mismatch")


def assess_frontier_benchmark_integrity(
    *,
    source: Frontier3CertificationArtifact,
    tenant_id: str,
    company_id: str,
    checked_at: datetime,
    current_jarvis_system_version: str,
    jarvis_measurements: tuple[JarvisDomainMeasurement, ...],
    frontier_measurements: tuple[FrontierSystemMeasurement, ...],
    audits: tuple[MeasurementIntegrityAudit, ...],
    current_frontier_releases: tuple[CurrentFrontierRelease, ...],
    current_protocols: tuple[CurrentBenchmarkProtocol, ...],
    certification_policy: Frontier3CertificationPolicy,
    integrity_policy: BenchmarkIntegrityPolicy | None = None,
) -> FrontierBenchmarkIntegrityArtifact:
    """Revalidate certificate integrity against contamination and frontier drift."""

    source = Frontier3CertificationArtifact.model_validate(source.model_dump(mode="json"))
    if source.tenant_id != tenant_id:
        raise ValueError("frontier_integrity_cross_tenant_source_forbidden")
    if source.company_id != company_id:
        raise ValueError("frontier_integrity_cross_company_source_forbidden")
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("frontier_integrity_check_requires_timezone")
    if checked_at < source.assessed_at:
        raise ValueError("frontier_integrity_check_cannot_precede_certification")

    rules = integrity_policy or BenchmarkIntegrityPolicy()
    jarvis_measurements = tuple(
        JarvisDomainMeasurement.model_validate(item.model_dump(mode="json"))
        for item in jarvis_measurements
    )
    frontier_measurements = tuple(
        FrontierSystemMeasurement.model_validate(item.model_dump(mode="json"))
        for item in frontier_measurements
    )
    audits = tuple(MeasurementIntegrityAudit.model_validate(item.model_dump(mode="json")) for item in audits)
    current_frontier_releases = tuple(
        CurrentFrontierRelease.model_validate(item.model_dump(mode="json"))
        for item in current_frontier_releases
    )
    current_protocols = tuple(
        CurrentBenchmarkProtocol.model_validate(item.model_dump(mode="json"))
        for item in current_protocols
    )
    certification_policy = Frontier3CertificationPolicy.model_validate(
        certification_policy.model_dump(mode="json")
    )

    _replay_source_certification(
        source=source,
        jarvis_measurements=jarvis_measurements,
        frontier_measurements=frontier_measurements,
        certification_policy=certification_policy,
    )

    audit_ids = [item.audit_id for item in audits]
    if len(audit_ids) != len(set(audit_ids)):
        raise ValueError("frontier_integrity_audit_ids_must_be_unique")
    release_families = [item.provider_family for item in current_frontier_releases]
    if len(release_families) != len(set(release_families)):
        raise ValueError("frontier_integrity_one_current_release_per_provider_required")
    protocol_domains = [item.domain for item in current_protocols]
    if len(protocol_domains) != len(set(protocol_domains)):
        raise ValueError("frontier_integrity_one_current_protocol_per_domain_required")

    blockers: list[str] = []
    revoke = False
    evidence: set[str] = set(source.evidence_refs)
    if source.disposition is not Frontier3MatrixDisposition.CERTIFIED:
        blockers.append("frontier_integrity_source_matrix_not_certified")

    if current_jarvis_system_version != source.jarvis_system_version:
        blockers.append("frontier_integrity_jarvis_version_drift")

    measurements: dict[str, tuple[str, str, FrontierCertificationDomain, datetime]] = {}
    evaluator_by_measurement: dict[str, str] = {}
    for item in jarvis_measurements:
        measurements[item.measurement_id] = (
            source.jarvis_system_id,
            item.system_version,
            item.domain,
            item.measured_at,
        )
        evaluator_by_measurement[item.measurement_id] = item.independent_evaluator_ref
        evidence.update(item.evidence_refs)
    for item in frontier_measurements:
        if item.measurement_id in measurements:
            raise ValueError("frontier_integrity_measurement_ids_must_be_globally_unique")
        measurements[item.measurement_id] = (
            item.system_id,
            item.system_version,
            item.domain,
            item.measured_at,
        )
        evaluator_by_measurement[item.measurement_id] = item.independent_evaluator_ref
        evidence.update(item.evidence_refs)
        evidence.add(item.frontier_qualification_evidence_ref)

    unknown_audits = {item.measurement_id for item in audits} - set(measurements)
    if unknown_audits:
        raise ValueError("frontier_integrity_audit_references_unknown_measurement")

    for measurement_id, (_, _, _, measured_at) in measurements.items():
        if checked_at - measured_at > timedelta(days=certification_policy.maximum_benchmark_age_days):
            blockers.append(f"frontier_integrity_measurement_now_stale:{measurement_id}")

        items = [item for item in audits if item.measurement_id == measurement_id]
        independent = [
            item
            for item in items
            if item.independent_auditor
            and item.auditor_ref != evaluator_by_measurement[measurement_id]
        ]
        auditor_refs = {item.auditor_ref for item in independent}
        if len(auditor_refs) < rules.minimum_independent_auditors:
            blockers.append(f"frontier_integrity_auditor_quorum_missing:{measurement_id}")

        for audit in independent:
            evidence.update(audit.evidence_refs)
            if audit.audited_at > checked_at:
                blockers.append(f"frontier_integrity_future_audit_forbidden:{measurement_id}")
            if rules.require_hidden_or_rotated_eval and audit.exposure_mode is BenchmarkExposureMode.PUBLIC_STATIC:
                blockers.append(f"frontier_integrity_public_static_eval_not_admissible:{measurement_id}")
            if audit.unseen_item_fraction < rules.minimum_unseen_item_fraction:
                blockers.append(f"frontier_integrity_unseen_fraction_insufficient:{measurement_id}")
            if audit.known_public_overlap_fraction > rules.maximum_public_overlap_fraction:
                blockers.append(f"frontier_integrity_public_overlap_excessive:{measurement_id}")
            if audit.prompt_answer_leakage_detected:
                blockers.append(f"frontier_integrity_prompt_answer_leakage:{measurement_id}")
                revoke = True
            if audit.contamination_detected:
                blockers.append(f"frontier_integrity_contamination_detected:{measurement_id}")
                revoke = True

    releases = {item.provider_family: item for item in current_frontier_releases}
    for release in current_frontier_releases:
        evidence.add(release.evidence_ref)
        if release.released_at > checked_at:
            blockers.append(f"frontier_integrity_future_release_forbidden:{release.provider_family}")

    for peer in frontier_measurements:
        release = releases.get(peer.provider_family)
        if release is None:
            blockers.append(f"frontier_integrity_current_frontier_release_missing:{peer.provider_family}")
            continue
        changed = (release.system_id, release.system_version) != (peer.system_id, peer.system_version)
        if release.benchmark_eligible and changed and release.released_at > peer.measured_at:
            blockers.append(f"frontier_integrity_newer_frontier_release_requires_rebenchmark:{peer.provider_family}")

    protocols = {item.domain: item for item in current_protocols}
    jarvis_by_domain = {item.domain: item for item in jarvis_measurements}
    for protocol in current_protocols:
        evidence.add(protocol.evidence_ref)
        if protocol.effective_at > checked_at:
            blockers.append(f"frontier_integrity_future_protocol_forbidden:{protocol.domain.value}")

    for domain in source.required_domains:
        current = protocols.get(domain)
        measured = jarvis_by_domain.get(domain)
        if current is None:
            blockers.append(f"frontier_integrity_current_protocol_missing:{domain.value}")
            continue
        if measured is None:
            blockers.append(f"frontier_integrity_jarvis_measurement_missing:{domain.value}")
            continue
        if _protocol_key(current.protocol) != _protocol_key(measured.protocol) and current.effective_at > measured.measured_at:
            blockers.append(f"frontier_integrity_protocol_rotated_requires_rebenchmark:{domain.value}")

    unique_blockers = tuple(dict.fromkeys(blockers))
    if revoke:
        validity = FrontierBenchmarkValidity.REVOKED
    elif unique_blockers:
        validity = FrontierBenchmarkValidity.HOLD
    else:
        validity = FrontierBenchmarkValidity.VALID

    values = {
        "contract": FRONTIER_BENCHMARK_INTEGRITY_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "source_certification_fingerprint": source.fingerprint,
        "source_certification_id": source.certification_id,
        "source_jarvis_system_version": source.jarvis_system_version,
        "current_jarvis_system_version": current_jarvis_system_version,
        "checked_at": checked_at,
        "audited_measurement_count": len({item.measurement_id for item in audits}),
        "frontier_release_count": len(current_frontier_releases),
        "current_protocol_count": len(current_protocols),
        "validity": validity,
        "blockers": unique_blockers,
        "evidence_refs": tuple(sorted(evidence)),
        "bounded_matrix_parity_claim_still_valid": (
            validity is FrontierBenchmarkValidity.VALID
            and source.bounded_matrix_parity_claim_allowed
        ),
        "bounded_matrix_superiority_claim_still_valid": (
            validity is FrontierBenchmarkValidity.VALID
            and source.bounded_matrix_measured_superiority_claim_allowed
        ),
        "universal_superiority_claim_allowed": False,
        "company_truth_promoted": False,
        "provider_authority_granted": False,
        "automatic_training_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
    }
    draft = FrontierBenchmarkIntegrityArtifact.model_construct(**values, fingerprint="0" * 64)
    return FrontierBenchmarkIntegrityArtifact(**values, fingerprint=_seal(_payload(draft)))
