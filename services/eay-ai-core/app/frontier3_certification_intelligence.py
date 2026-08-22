"""Frontier-3 portfolio certification authority for Jarvis.

This layer turns frontier parity into a replayable domain-by-domain matrix rather
than a slogan. Jarvis is compared against at least three independently evaluated,
provider-diverse frontier systems under the same benchmark protocol, task set,
environment, scenario coverage and as-of boundary.

A certified artifact authorizes only bounded measured claims over included domains.
It never authorizes a universal superiority claim, Company Truth promotion,
provider selection, model/policy mutation, execution or side effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

FRONTIER3_CERTIFICATION_CONTRACT = "eay-frontier3-certification-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FrontierCertificationDomain(str, Enum):
    GENERAL_REASONING = "general_reasoning"
    SOFTWARE_ENGINEERING = "software_engineering"
    GENERAL_KNOWLEDGE = "general_knowledge"
    DEEP_RESEARCH = "deep_research"
    NOVEL_PROBLEM_SOLVING = "novel_problem_solving"
    MULTIMODAL_WORLD = "multimodal_world"
    MATHEMATICS_DATA_ANALYSIS = "mathematics_data_analysis"
    LONG_CONTEXT = "long_context"
    LIVE_WORLD_KNOWLEDGE = "live_world_knowledge"
    SELF_CORRECTION = "self_correction"
    LONG_HORIZON_AGENTIC = "long_horizon_agentic"
    MULTI_AGENT_ORCHESTRATION = "multi_agent_orchestration"
    DURABLE_OBJECTIVE_WORK = "durable_objective_work"
    BUSINESS_DOMAIN_REASONING = "business_domain_reasoning"


_ALL_DOMAINS = tuple(FrontierCertificationDomain)


class FrontierCertificationStatus(str, Enum):
    HOLD = "hold"
    BELOW_FRONTIER = "below_frontier"
    FRONTIER_PARITY = "frontier_parity"
    STATISTICALLY_SUPERIOR = "statistically_superior"


class Frontier3MatrixDisposition(str, Enum):
    CERTIFIED = "certified"
    HOLD = "hold"


class BenchmarkScenarioCoverage(SealedModel):
    holdout: bool
    out_of_distribution: bool
    adversarial: bool
    temporal: bool

    @property
    def complete(self) -> bool:
        return all(
            (
                self.holdout,
                self.out_of_distribution,
                self.adversarial,
                self.temporal,
            )
        )


class BenchmarkProtocolIdentity(SealedModel):
    protocol_id: str = Field(pattern=_SCOPE)
    protocol_version: str = Field(pattern=_SCOPE)
    task_set_id: str = Field(pattern=_SCOPE)
    task_set_fingerprint: str = Field(pattern=_DIGEST)
    environment_fingerprint: str = Field(pattern=_DIGEST)
    metric_set_fingerprint: str = Field(pattern=_DIGEST)


class FrontierSystemMeasurement(SealedModel):
    measurement_id: str = Field(pattern=_SCOPE)
    domain: FrontierCertificationDomain
    system_id: str = Field(pattern=_SCOPE)
    system_version: str = Field(pattern=_SCOPE)
    provider_family: str = Field(pattern=_SCOPE)
    normalized_score: float = Field(ge=0.0, le=1.0)
    confidence_lower: float = Field(ge=0.0, le=1.0)
    confidence_upper: float = Field(ge=0.0, le=1.0)
    confidence_level: float = Field(default=0.95, ge=0.90, le=0.999)
    sample_count: int = Field(ge=1)
    measured_at: datetime
    protocol: BenchmarkProtocolIdentity
    scenario_coverage: BenchmarkScenarioCoverage
    independent_evaluator_ref: str = Field(pattern=_SCOPE)
    frontier_qualification_evidence_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=2)
    frontier_qualified: bool

    @model_validator(mode="after")
    def measurement_is_integral(self) -> "FrontierSystemMeasurement":
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("frontier3_measurement_requires_timezone")
        if not self.confidence_lower <= self.normalized_score <= self.confidence_upper:
            raise ValueError("frontier3_score_must_lie_inside_confidence_interval")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("frontier3_measurement_evidence_refs_must_be_unique")
        return self


class JarvisDomainMeasurement(SealedModel):
    measurement_id: str = Field(pattern=_SCOPE)
    domain: FrontierCertificationDomain
    system_version: str = Field(pattern=_SCOPE)
    normalized_score: float = Field(ge=0.0, le=1.0)
    confidence_lower: float = Field(ge=0.0, le=1.0)
    confidence_upper: float = Field(ge=0.0, le=1.0)
    confidence_level: float = Field(default=0.95, ge=0.90, le=0.999)
    sample_count: int = Field(ge=1)
    measured_at: datetime
    protocol: BenchmarkProtocolIdentity
    scenario_coverage: BenchmarkScenarioCoverage
    independent_evaluator_ref: str = Field(pattern=_SCOPE)
    evidence_refs: tuple[str, ...] = Field(min_length=2)
    critical_safety_regression: bool = False

    @model_validator(mode="after")
    def measurement_is_integral(self) -> "JarvisDomainMeasurement":
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("frontier3_measurement_requires_timezone")
        if not self.confidence_lower <= self.normalized_score <= self.confidence_upper:
            raise ValueError("frontier3_score_must_lie_inside_confidence_interval")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("frontier3_measurement_evidence_refs_must_be_unique")
        return self


class Frontier3CertificationPolicy(SealedModel):
    minimum_provider_families: int = Field(default=3, ge=3, le=8)
    minimum_sample_count: int = Field(default=100, ge=20, le=1000000)
    maximum_benchmark_age_days: int = Field(default=30, ge=1, le=180)
    minimum_confidence_level: float = Field(default=0.95, ge=0.90, le=0.999)
    superiority_margin: float = Field(default=0.0, ge=0.0, le=0.20)
    require_complete_scenario_coverage: bool = True
    required_domains: tuple[FrontierCertificationDomain, ...] = _ALL_DOMAINS

    @model_validator(mode="after")
    def policy_is_strict(self) -> "Frontier3CertificationPolicy":
        if not self.require_complete_scenario_coverage:
            raise ValueError("frontier3_complete_scenario_coverage_cannot_be_disabled")
        if not self.required_domains:
            raise ValueError("frontier3_required_domains_cannot_be_empty")
        if len(self.required_domains) != len(set(self.required_domains)):
            raise ValueError("frontier3_required_domains_must_be_unique")
        return self


class FrontierDomainCertification(SealedModel):
    domain: FrontierCertificationDomain
    jarvis_score: float = Field(ge=0.0, le=1.0)
    jarvis_confidence_lower: float = Field(ge=0.0, le=1.0)
    jarvis_confidence_upper: float = Field(ge=0.0, le=1.0)
    strongest_frontier_score: float = Field(ge=0.0, le=1.0)
    strongest_frontier_confidence_lower: float = Field(ge=0.0, le=1.0)
    strongest_frontier_confidence_upper: float = Field(ge=0.0, le=1.0)
    strongest_frontier_system_id: str | None = None
    eligible_provider_families: tuple[str, ...]
    status: FrontierCertificationStatus
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    bounded_parity_claim_allowed: bool
    bounded_measured_superiority_claim_allowed: bool

    @model_validator(mode="after")
    def claim_matches_status(self) -> "FrontierDomainCertification":
        if self.status is FrontierCertificationStatus.STATISTICALLY_SUPERIOR:
            if not (
                self.bounded_parity_claim_allowed
                and self.bounded_measured_superiority_claim_allowed
                and not self.blockers
            ):
                raise ValueError("frontier3_superior_status_requires_clean_bounded_claims")
        elif self.status is FrontierCertificationStatus.FRONTIER_PARITY:
            if not self.bounded_parity_claim_allowed:
                raise ValueError("frontier3_parity_status_requires_bounded_parity_claim")
            if self.bounded_measured_superiority_claim_allowed:
                raise ValueError("frontier3_parity_cannot_claim_measured_superiority")
        elif self.bounded_parity_claim_allowed or self.bounded_measured_superiority_claim_allowed:
            raise ValueError("frontier3_hold_or_below_cannot_allow_claim")
        return self


class Frontier3CertificationArtifact(SealedModel):
    contract: str = FRONTIER3_CERTIFICATION_CONTRACT
    certification_id: str = Field(pattern=_SCOPE)
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    jarvis_system_id: str = Field(pattern=_SCOPE)
    jarvis_system_version: str = Field(pattern=_SCOPE)
    assessed_at: datetime
    required_domains: tuple[FrontierCertificationDomain, ...]
    domain_certifications: tuple[FrontierDomainCertification, ...]
    certified_domain_count: int = Field(ge=0)
    superiority_domain_count: int = Field(ge=0)
    disposition: Frontier3MatrixDisposition
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    complete_frontier3_matrix: bool
    bounded_matrix_parity_claim_allowed: bool
    bounded_matrix_measured_superiority_claim_allowed: bool
    universal_superiority_claim_allowed: bool = False
    company_truth_promoted: bool = False
    provider_authority_granted: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def artifact_is_integral_and_non_authoritative(self) -> "Frontier3CertificationArtifact":
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() is None:
            raise ValueError("frontier3_assessment_requires_timezone")
        if any(
            (
                self.universal_superiority_claim_allowed,
                self.company_truth_promoted,
                self.provider_authority_granted,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("frontier3_certification_never_mints_universal_or_execution_authority")
        if self.disposition is Frontier3MatrixDisposition.CERTIFIED:
            if self.blockers or not self.bounded_matrix_parity_claim_allowed:
                raise ValueError("frontier3_certified_matrix_requires_clean_bounded_parity_claim")
        elif (
            self.bounded_matrix_parity_claim_allowed
            or self.bounded_matrix_measured_superiority_claim_allowed
        ):
            raise ValueError("frontier3_hold_matrix_cannot_allow_claim")
        if self.bounded_matrix_measured_superiority_claim_allowed and (
            not self.complete_frontier3_matrix
            or self.superiority_domain_count != len(self.required_domains)
        ):
            raise ValueError("frontier3_matrix_superiority_requires_complete_all_domain_superiority")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("frontier3_certification_fingerprint_mismatch")
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


def _measurement_blockers(
    *,
    measured_at: datetime,
    assessed_at: datetime,
    sample_count: int,
    confidence_level: float,
    scenario_coverage: BenchmarkScenarioCoverage,
    policy: Frontier3CertificationPolicy,
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    if measured_at > assessed_at:
        blockers.append(f"{prefix}_future_measurement_forbidden")
    elif assessed_at - measured_at > timedelta(days=policy.maximum_benchmark_age_days):
        blockers.append(f"{prefix}_benchmark_stale")
    if sample_count < policy.minimum_sample_count:
        blockers.append(f"{prefix}_sample_count_insufficient")
    if confidence_level < policy.minimum_confidence_level:
        blockers.append(f"{prefix}_confidence_level_insufficient")
    if policy.require_complete_scenario_coverage and not scenario_coverage.complete:
        blockers.append(f"{prefix}_scenario_coverage_incomplete")
    return blockers


def _certify_domain(
    *,
    domain: FrontierCertificationDomain,
    jarvis: JarvisDomainMeasurement | None,
    peers: tuple[FrontierSystemMeasurement, ...],
    assessed_at: datetime,
    policy: Frontier3CertificationPolicy,
) -> FrontierDomainCertification:
    if jarvis is None:
        return FrontierDomainCertification(
            domain=domain,
            jarvis_score=0.0,
            jarvis_confidence_lower=0.0,
            jarvis_confidence_upper=0.0,
            strongest_frontier_score=0.0,
            strongest_frontier_confidence_lower=0.0,
            strongest_frontier_confidence_upper=0.0,
            strongest_frontier_system_id=None,
            eligible_provider_families=(),
            status=FrontierCertificationStatus.HOLD,
            blockers=("frontier3_jarvis_domain_measurement_missing",),
            evidence_refs=(),
            bounded_parity_claim_allowed=False,
            bounded_measured_superiority_claim_allowed=False,
        )

    blockers: list[str] = []
    evidence: set[str] = set(jarvis.evidence_refs)
    blockers.extend(
        _measurement_blockers(
            measured_at=jarvis.measured_at,
            assessed_at=assessed_at,
            sample_count=jarvis.sample_count,
            confidence_level=jarvis.confidence_level,
            scenario_coverage=jarvis.scenario_coverage,
            policy=policy,
            prefix="frontier3_jarvis",
        )
    )
    if jarvis.critical_safety_regression:
        blockers.append("frontier3_jarvis_critical_safety_regression")

    protocol_key = _protocol_key(jarvis.protocol)
    evaluator_refs = {jarvis.independent_evaluator_ref}
    eligible_peers: list[FrontierSystemMeasurement] = []
    for peer in peers:
        evidence.update(peer.evidence_refs)
        evidence.add(peer.frontier_qualification_evidence_ref)
        peer_blockers: list[str] = []
        if not peer.frontier_qualified:
            peer_blockers.append(f"frontier3_peer_not_frontier_qualified:{peer.system_id}")
        peer_blockers.extend(
            _measurement_blockers(
                measured_at=peer.measured_at,
                assessed_at=assessed_at,
                sample_count=peer.sample_count,
                confidence_level=peer.confidence_level,
                scenario_coverage=peer.scenario_coverage,
                policy=policy,
                prefix=f"frontier3_peer:{peer.system_id}",
            )
        )
        if _protocol_key(peer.protocol) != protocol_key:
            peer_blockers.append(f"frontier3_protocol_mismatch:{peer.system_id}")
        if peer.independent_evaluator_ref in evaluator_refs:
            peer_blockers.append(f"frontier3_evaluator_independence_missing:{peer.system_id}")
        evaluator_refs.add(peer.independent_evaluator_ref)
        if peer_blockers:
            blockers.extend(peer_blockers)
        else:
            eligible_peers.append(peer)

    provider_families = [peer.provider_family for peer in eligible_peers]
    if len(set(provider_families)) < policy.minimum_provider_families:
        blockers.append("frontier3_provider_diversity_insufficient")
    if len(provider_families) != len(set(provider_families)):
        blockers.append("frontier3_peer_provider_family_must_be_unique")

    system_ids = [peer.system_id for peer in eligible_peers]
    if len(system_ids) != len(set(system_ids)):
        blockers.append("frontier3_peer_system_ids_must_be_unique")

    strongest = max(
        eligible_peers,
        key=lambda item: (
            item.normalized_score,
            item.confidence_lower,
            item.confidence_upper,
            item.system_id,
        ),
        default=None,
    )
    if strongest is None:
        blockers.append("frontier3_no_eligible_frontier_peer")

    if blockers or strongest is None:
        status = FrontierCertificationStatus.HOLD
        parity_allowed = False
        superior_allowed = False
    elif jarvis.normalized_score < strongest.normalized_score:
        status = FrontierCertificationStatus.BELOW_FRONTIER
        blockers.append("frontier3_jarvis_below_strongest_frontier")
        parity_allowed = False
        superior_allowed = False
    else:
        maximum_peer_upper = max(peer.confidence_upper for peer in eligible_peers)
        statistically_superior = (
            jarvis.confidence_lower > maximum_peer_upper + policy.superiority_margin
        )
        if statistically_superior:
            status = FrontierCertificationStatus.STATISTICALLY_SUPERIOR
            parity_allowed = True
            superior_allowed = True
        else:
            status = FrontierCertificationStatus.FRONTIER_PARITY
            parity_allowed = True
            superior_allowed = False

    strongest_score = strongest.normalized_score if strongest else 0.0
    strongest_lower = strongest.confidence_lower if strongest else 0.0
    strongest_upper = strongest.confidence_upper if strongest else 0.0
    strongest_id = strongest.system_id if strongest else None

    return FrontierDomainCertification(
        domain=domain,
        jarvis_score=jarvis.normalized_score,
        jarvis_confidence_lower=jarvis.confidence_lower,
        jarvis_confidence_upper=jarvis.confidence_upper,
        strongest_frontier_score=strongest_score,
        strongest_frontier_confidence_lower=strongest_lower,
        strongest_frontier_confidence_upper=strongest_upper,
        strongest_frontier_system_id=strongest_id,
        eligible_provider_families=tuple(sorted(set(provider_families))),
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_refs=tuple(sorted(evidence)),
        bounded_parity_claim_allowed=parity_allowed,
        bounded_measured_superiority_claim_allowed=superior_allowed,
    )


def certify_frontier3_matrix(
    *,
    certification_id: str,
    tenant_id: str,
    company_id: str,
    jarvis_system_id: str,
    jarvis_system_version: str,
    assessed_at: datetime,
    jarvis_measurements: tuple[JarvisDomainMeasurement, ...],
    frontier_measurements: tuple[FrontierSystemMeasurement, ...],
    policy: Frontier3CertificationPolicy | None = None,
) -> Frontier3CertificationArtifact:
    """Certify measured Frontier-3 parity without converting benchmark results into authority."""

    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("frontier3_assessment_requires_timezone")
    rules = policy or Frontier3CertificationPolicy()
    jarvis_measurements = tuple(
        JarvisDomainMeasurement.model_validate(item.model_dump(mode="json"))
        for item in jarvis_measurements
    )
    frontier_measurements = tuple(
        FrontierSystemMeasurement.model_validate(item.model_dump(mode="json"))
        for item in frontier_measurements
    )

    jarvis_ids = [item.measurement_id for item in jarvis_measurements]
    frontier_ids = [item.measurement_id for item in frontier_measurements]
    if len(jarvis_ids) != len(set(jarvis_ids)):
        raise ValueError("frontier3_jarvis_measurement_ids_must_be_unique")
    if len(frontier_ids) != len(set(frontier_ids)):
        raise ValueError("frontier3_peer_measurement_ids_must_be_unique")

    by_domain_jarvis: dict[FrontierCertificationDomain, JarvisDomainMeasurement] = {}
    for item in jarvis_measurements:
        if item.domain in by_domain_jarvis:
            raise ValueError("frontier3_one_jarvis_measurement_per_domain_required")
        if item.system_version != jarvis_system_version:
            raise ValueError("frontier3_jarvis_system_version_mismatch")
        by_domain_jarvis[item.domain] = item

    domain_certifications = tuple(
        _certify_domain(
            domain=domain,
            jarvis=by_domain_jarvis.get(domain),
            peers=tuple(item for item in frontier_measurements if item.domain is domain),
            assessed_at=assessed_at,
            policy=rules,
        )
        for domain in rules.required_domains
    )

    matrix_blockers = tuple(
        f"frontier3_domain_not_certified:{item.domain.value}:{item.status.value}"
        for item in domain_certifications
        if item.status
        in {FrontierCertificationStatus.HOLD, FrontierCertificationStatus.BELOW_FRONTIER}
    )
    certified_count = sum(
        item.status
        in {
            FrontierCertificationStatus.FRONTIER_PARITY,
            FrontierCertificationStatus.STATISTICALLY_SUPERIOR,
        }
        for item in domain_certifications
    )
    superiority_count = sum(
        item.status is FrontierCertificationStatus.STATISTICALLY_SUPERIOR
        for item in domain_certifications
    )
    complete_matrix = set(rules.required_domains) == set(_ALL_DOMAINS)
    disposition = (
        Frontier3MatrixDisposition.CERTIFIED
        if not matrix_blockers
        else Frontier3MatrixDisposition.HOLD
    )
    bounded_matrix_parity = disposition is Frontier3MatrixDisposition.CERTIFIED
    bounded_matrix_superiority = (
        bounded_matrix_parity
        and complete_matrix
        and superiority_count == len(rules.required_domains)
    )
    all_evidence = tuple(
        sorted({ref for item in domain_certifications for ref in item.evidence_refs})
    )

    values = {
        "contract": FRONTIER3_CERTIFICATION_CONTRACT,
        "certification_id": certification_id,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "jarvis_system_id": jarvis_system_id,
        "jarvis_system_version": jarvis_system_version,
        "assessed_at": assessed_at,
        "required_domains": rules.required_domains,
        "domain_certifications": domain_certifications,
        "certified_domain_count": certified_count,
        "superiority_domain_count": superiority_count,
        "disposition": disposition,
        "blockers": matrix_blockers,
        "evidence_refs": all_evidence,
        "complete_frontier3_matrix": complete_matrix,
        "bounded_matrix_parity_claim_allowed": bounded_matrix_parity,
        "bounded_matrix_measured_superiority_claim_allowed": bounded_matrix_superiority,
        "universal_superiority_claim_allowed": False,
        "company_truth_promoted": False,
        "provider_authority_granted": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
    }
    draft = Frontier3CertificationArtifact.model_construct(
        **values,
        fingerprint="0" * 64,
    )
    return Frontier3CertificationArtifact(
        **values,
        fingerprint=_seal(_payload(draft)),
    )
