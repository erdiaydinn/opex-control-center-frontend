"""Defensive cyber-security school and graduation gate for EAY Jarvis.

The school expands Jarvis' defensive knowledge while preserving a strict
non-offensive authority boundary. Public threat knowledge is useful for
recognition, detection and mitigation planning, but never proves company
exposure or an incident and never grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_benchmark_intelligence import CyberBenchmarkComparison

CYBER_DEFENSE_SCHOOL_CONTRACT = "eay-cyber-defense-school-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|"
    r"persistence[_-]?payload|ransomware[_-]?payload|shellcode)"
)


class CyberDefenseDomain(str, Enum):
    WEB_API = "web_api"
    IDENTITY = "identity"
    CLOUD_CONTAINER = "cloud_container"
    ENDPOINT_NETWORK = "endpoint_network"
    SOFTWARE_SUPPLY_CHAIN = "software_supply_chain"
    DATA_SECURITY = "data_security"
    MOBILE_DEVICE = "mobile_device"
    AI_AGENTIC = "ai_agentic"
    INSIDER_SOCIAL = "insider_social"
    IOT_OT = "iot_ot"
    INCIDENT_RESPONSE_DETECTION = "incident_response_detection"


class CyberKnowledgeSource(str, Enum):
    MITRE_ATTACK = "mitre_attack"
    MITRE_D3FEND = "mitre_d3fend"
    CISA_KEV = "cisa_kev"
    FIRST_EPSS = "first_epss"
    NVD_CVE = "nvd_cve"
    CWE = "cwe"
    CAPEC = "capec"
    OWASP_ASVS = "owasp_asvs"
    OWASP_API = "owasp_api"
    OWASP_MOBILE = "owasp_mobile"
    OWASP_GENAI = "owasp_genai"
    VENDOR_ADVISORY = "vendor_advisory"
    GITHUB_SECURITY_ADVISORY = "github_security_advisory"
    SIGMA = "sigma"
    YARA = "yara"
    NIST_CSF = "nist_csf"


class CyberSourceAuthority(str, Enum):
    ATTACK_BEHAVIOR = "attack_behavior"
    DEFENSIVE_COUNTERMEASURE = "defensive_countermeasure"
    KNOWN_EXPLOITATION = "known_exploitation"
    EXPLOITATION_PROBABILITY = "exploitation_probability"
    VULNERABILITY_METADATA = "vulnerability_metadata"
    WEAKNESS_TAXONOMY = "weakness_taxonomy"
    ATTACK_PATTERN_TAXONOMY = "attack_pattern_taxonomy"
    APPLICATION_DEFENSE = "application_defense"
    AI_DEFENSE = "ai_defense"
    PRODUCT_ADVISORY = "product_advisory"
    DEPENDENCY_ADVISORY = "dependency_advisory"
    DETECTION_CONTENT = "detection_content"
    SECURITY_FRAMEWORK = "security_framework"


class CyberKnowledgeSourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_SCHOOL_CONTRACT
    source: CyberKnowledgeSource
    authority: CyberSourceAuthority
    source_ref: str = Field(min_length=1)
    server_side_only: bool = True
    maximum_observation_age_seconds: int = Field(gt=0)
    can_assert_known_exploitation: bool = False
    can_assert_company_exposure: bool = False
    can_confirm_company_incident: bool = False
    attack_instruction_content_allowed: bool = False
    exploit_generation_permitted: bool = False
    credential_capture_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def source_policy_is_defensive(self) -> CyberKnowledgeSourcePolicy:
        if not self.server_side_only:
            raise ValueError("cyber_school_source_must_be_server_side")
        if self.can_assert_known_exploitation != (
            self.source is CyberKnowledgeSource.CISA_KEV
        ):
            raise ValueError("cyber_school_known_exploitation_authority_invalid")
        if self.can_assert_company_exposure:
            raise ValueError("cyber_school_public_source_never_proves_company_exposure")
        if self.can_confirm_company_incident:
            raise ValueError("cyber_school_public_source_never_confirms_company_incident")
        if self.attack_instruction_content_allowed:
            raise ValueError("cyber_school_attack_instruction_content_forbidden")
        if self.exploit_generation_permitted:
            raise ValueError("cyber_school_exploit_generation_forbidden")
        if self.credential_capture_permitted:
            raise ValueError("cyber_school_credential_capture_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_school_source_never_grants_execution_authority")
        _safe_ref(self.source_ref, "cyber_school_source_ref_unsafe")
        _verify(self, "cyber_school_source_policy_fingerprint_mismatch")
        return self


class CyberDefenseCurriculum(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_SCHOOL_CONTRACT
    curriculum_id: str = Field(min_length=1)
    domains: tuple[CyberDefenseDomain, ...] = Field(min_length=1)
    source_policies: tuple[CyberKnowledgeSourcePolicy, ...] = Field(min_length=1)
    required_sources_by_domain: dict[CyberDefenseDomain, tuple[CyberKnowledgeSource, ...]]
    architecture_evidence_required: bool = True
    exploit_generation_permitted: bool = False
    destructive_execution_permitted: bool = False
    production_mutation_permitted: bool = False
    automatic_remediation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def curriculum_is_complete_and_defensive(self) -> CyberDefenseCurriculum:
        expected_domains = set(CyberDefenseDomain)
        if set(self.domains) != expected_domains:
            raise ValueError("cyber_school_domains_must_be_complete")
        if len(self.domains) != len(set(self.domains)):
            raise ValueError("cyber_school_domains_must_be_unique")

        policies = {item.source: item for item in self.source_policies}
        if len(policies) != len(self.source_policies):
            raise ValueError("cyber_school_source_policies_must_be_unique")
        if set(policies) != set(CyberKnowledgeSource):
            raise ValueError("cyber_school_source_policies_must_be_complete")
        for policy in self.source_policies:
            CyberKnowledgeSourcePolicy.model_validate(policy.model_dump(mode="json"))

        if set(self.required_sources_by_domain) != expected_domains:
            raise ValueError("cyber_school_domain_source_map_must_be_complete")
        for domain, sources in self.required_sources_by_domain.items():
            if not sources:
                raise ValueError(f"cyber_school_domain_requires_sources:{domain.value}")
            if len(sources) != len(set(sources)):
                raise ValueError("cyber_school_domain_sources_must_be_unique")
            if any(source not in policies for source in sources):
                raise ValueError("cyber_school_domain_references_unknown_source")

        if not self.architecture_evidence_required:
            raise ValueError("cyber_school_architecture_evidence_is_mandatory")
        if (
            self.exploit_generation_permitted
            or self.destructive_execution_permitted
            or self.production_mutation_permitted
            or self.automatic_remediation_permitted
            or self.execution_authority_granted
        ):
            raise ValueError("cyber_school_never_creates_offensive_or_write_authority")
        _safe_ref(self.curriculum_id, "cyber_school_curriculum_ref_unsafe")
        _verify(self, "cyber_school_curriculum_fingerprint_mismatch")
        return self


class CyberSourceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_SCHOOL_CONTRACT
    source: CyberKnowledgeSource
    source_version_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_temporal_and_safe(self) -> CyberSourceObservation:
        _aware(self.observed_at, "cyber_school_source_observed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_school_source_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("cyber_school_source_recorded_before_observed")
        for ref in (self.source_version_ref, self.evidence_ref):
            _safe_ref(ref, "cyber_school_source_observation_ref_unsafe")
        _verify(self, "cyber_school_source_observation_fingerprint_mismatch")
        return self


class CyberDefenseDomainReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_SCHOOL_CONTRACT
    receipt_id: str = Field(min_length=1)
    curriculum_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    domain: CyberDefenseDomain
    as_of: datetime
    source_observations: tuple[CyberSourceObservation, ...] = Field(min_length=1)
    attack_behavior_refs: tuple[str, ...] = ()
    weakness_refs: tuple[str, ...] = ()
    detection_refs: tuple[str, ...] = ()
    mitigation_refs: tuple[str, ...] = ()
    eay_surface_refs: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    unresolved_questions: tuple[str, ...] = ()
    source_coverage_complete: bool
    source_freshness_complete: bool
    architecture_awareness_complete: bool
    defensive_reasoning_ready: bool
    company_exposure_granted: bool = False
    incident_confirmation_granted: bool = False
    exploit_generation_permitted: bool = False
    automatic_remediation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_defensive_and_evidence_bound(self) -> CyberDefenseDomainReceipt:
        _aware(self.as_of, "cyber_school_receipt_as_of_requires_timezone")
        _unique(
            tuple(item.source.value for item in self.source_observations),
            "cyber_school_receipt_sources_must_be_unique",
        )
        for observation in self.source_observations:
            CyberSourceObservation.model_validate(observation.model_dump(mode="json"))
            if observation.observed_at > self.as_of or observation.recorded_at > self.as_of:
                raise ValueError("cyber_school_receipt_contains_future_observation")

        for values in (
            self.attack_behavior_refs,
            self.weakness_refs,
            self.detection_refs,
            self.mitigation_refs,
            self.eay_surface_refs,
            self.evidence_refs,
            self.unresolved_questions,
        ):
            _unique(values, "cyber_school_receipt_refs_must_be_unique")
            for ref in values:
                _safe_ref(ref, "cyber_school_receipt_ref_unsafe")

        expected_ready = (
            self.source_coverage_complete
            and self.source_freshness_complete
            and self.architecture_awareness_complete
            and not self.unresolved_questions
        )
        if self.defensive_reasoning_ready != expected_ready:
            raise ValueError("cyber_school_receipt_readiness_mismatch")
        if self.company_exposure_granted:
            raise ValueError("cyber_school_learning_never_grants_company_exposure")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_school_learning_never_confirms_incident")
        if (
            self.exploit_generation_permitted
            or self.automatic_remediation_permitted
            or self.execution_authority_granted
        ):
            raise ValueError("cyber_school_receipt_never_grants_execution_authority")
        _verify(self, "cyber_school_domain_receipt_fingerprint_mismatch")
        return self


class CyberDefenseGraduationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_SCHOOL_CONTRACT
    curriculum_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    domain_receipt_fingerprints: tuple[str, ...] = Field(min_length=1)
    domain_coverage_complete: bool
    current_source_coverage_complete: bool
    architecture_awareness_complete: bool
    benchmark_superiority_proven: bool
    mentor_outperformance_claim_allowed: bool
    production_security_superiority_claim_allowed: bool = False
    blockers: tuple[str, ...] = ()
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def graduation_cannot_overclaim(self) -> CyberDefenseGraduationDecision:
        _unique(
            self.domain_receipt_fingerprints,
            "cyber_school_graduation_receipts_must_be_unique",
        )
        _unique(self.blockers, "cyber_school_graduation_blockers_must_be_unique")
        if self.production_security_superiority_claim_allowed:
            raise ValueError("cyber_school_never_proves_production_security_superiority")
        if self.mentor_outperformance_claim_allowed:
            if self.blockers:
                raise ValueError("cyber_school_outperformance_cannot_ignore_blockers")
            if not (
                self.domain_coverage_complete
                and self.current_source_coverage_complete
                and self.architecture_awareness_complete
                and self.benchmark_superiority_proven
            ):
                raise ValueError("cyber_school_outperformance_requires_all_gates")
        if self.exploit_generation_permitted or self.execution_authority_granted:
            raise ValueError("cyber_school_graduation_never_grants_execution_authority")
        _verify(self, "cyber_school_graduation_fingerprint_mismatch")
        return self


def default_cyber_defense_curriculum(
    *,
    curriculum_id: str = "eay-jarvis-cyber-defense-school-v1",
) -> CyberDefenseCurriculum:
    policies = tuple(_source_policy(source) for source in CyberKnowledgeSource)
    return _seal_model(
        CyberDefenseCurriculum,
        {
            "contract": CYBER_DEFENSE_SCHOOL_CONTRACT,
            "curriculum_id": curriculum_id,
            "domains": tuple(CyberDefenseDomain),
            "source_policies": policies,
            "required_sources_by_domain": _required_sources_by_domain(),
            "architecture_evidence_required": True,
            "exploit_generation_permitted": False,
            "destructive_execution_permitted": False,
            "production_mutation_permitted": False,
            "automatic_remediation_permitted": False,
            "execution_authority_granted": False,
        },
    )


def build_source_observation(
    *,
    source: CyberKnowledgeSource,
    source_version_ref: str,
    evidence_ref: str,
    observed_at: datetime,
    recorded_at: datetime,
) -> CyberSourceObservation:
    return _seal_model(
        CyberSourceObservation,
        {
            "contract": CYBER_DEFENSE_SCHOOL_CONTRACT,
            "source": source,
            "source_version_ref": source_version_ref,
            "evidence_ref": evidence_ref,
            "observed_at": observed_at,
            "recorded_at": recorded_at,
        },
    )


def build_domain_receipt(
    *,
    curriculum: CyberDefenseCurriculum,
    domain: CyberDefenseDomain,
    as_of: datetime,
    source_observations: tuple[CyberSourceObservation, ...],
    attack_behavior_refs: tuple[str, ...] = (),
    weakness_refs: tuple[str, ...] = (),
    detection_refs: tuple[str, ...] = (),
    mitigation_refs: tuple[str, ...] = (),
    eay_surface_refs: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    unresolved_questions: tuple[str, ...] = (),
) -> CyberDefenseDomainReceipt:
    curriculum = CyberDefenseCurriculum.model_validate(
        curriculum.model_dump(mode="json")
    )
    _aware(as_of, "cyber_school_receipt_as_of_requires_timezone")
    observations = tuple(
        CyberSourceObservation.model_validate(item.model_dump(mode="json"))
        for item in source_observations
    )
    by_source = {item.source: item for item in observations}
    if len(by_source) != len(observations):
        raise ValueError("cyber_school_receipt_sources_must_be_unique")

    required_sources = set(curriculum.required_sources_by_domain[domain])
    source_coverage_complete = required_sources.issubset(by_source)
    policy_by_source = {item.source: item for item in curriculum.source_policies}
    source_freshness_complete = source_coverage_complete and all(
        0 <= (as_of - by_source[source].observed_at).total_seconds()
        <= policy_by_source[source].maximum_observation_age_seconds
        for source in required_sources
    )
    architecture_complete = bool(eay_surface_refs and evidence_refs)
    ready = (
        source_coverage_complete
        and source_freshness_complete
        and architecture_complete
        and not unresolved_questions
    )
    seed = {
        "curriculum": curriculum.fingerprint,
        "domain": domain.value,
        "as_of": _iso(as_of),
        "sources": [item.fingerprint for item in observations],
        "eay_surface_refs": list(eay_surface_refs),
        "evidence_refs": list(evidence_refs),
    }
    return _seal_model(
        CyberDefenseDomainReceipt,
        {
            "contract": CYBER_DEFENSE_SCHOOL_CONTRACT,
            "receipt_id": f"cyber-school:{domain.value}:{_fingerprint(seed)[:24]}",
            "curriculum_fingerprint": curriculum.fingerprint,
            "domain": domain,
            "as_of": as_of,
            "source_observations": observations,
            "attack_behavior_refs": attack_behavior_refs,
            "weakness_refs": weakness_refs,
            "detection_refs": detection_refs,
            "mitigation_refs": mitigation_refs,
            "eay_surface_refs": eay_surface_refs,
            "evidence_refs": evidence_refs,
            "unresolved_questions": unresolved_questions,
            "source_coverage_complete": source_coverage_complete,
            "source_freshness_complete": source_freshness_complete,
            "architecture_awareness_complete": architecture_complete,
            "defensive_reasoning_ready": ready,
            "company_exposure_granted": False,
            "incident_confirmation_granted": False,
            "exploit_generation_permitted": False,
            "automatic_remediation_permitted": False,
            "execution_authority_granted": False,
        },
    )


def evaluate_cyber_defense_graduation(
    *,
    curriculum: CyberDefenseCurriculum,
    domain_receipts: tuple[CyberDefenseDomainReceipt, ...],
    benchmark: CyberBenchmarkComparison,
) -> CyberDefenseGraduationDecision:
    curriculum = CyberDefenseCurriculum.model_validate(
        curriculum.model_dump(mode="json")
    )
    benchmark = CyberBenchmarkComparison.model_validate(
        benchmark.model_dump(mode="json")
    )
    receipts = tuple(
        CyberDefenseDomainReceipt.model_validate(item.model_dump(mode="json"))
        for item in domain_receipts
    )
    by_domain = {item.domain: item for item in receipts}
    duplicate_domains = len(by_domain) != len(receipts)
    required_domains = set(curriculum.domains)
    curriculum_bound = all(
        item.curriculum_fingerprint == curriculum.fingerprint for item in receipts
    )
    domain_coverage_complete = (
        not duplicate_domains
        and set(by_domain) == required_domains
        and curriculum_bound
        and all(item.defensive_reasoning_ready for item in receipts)
    )
    source_coverage_complete = domain_coverage_complete and all(
        item.source_coverage_complete and item.source_freshness_complete
        for item in receipts
    )
    architecture_complete = domain_coverage_complete and all(
        item.architecture_awareness_complete for item in receipts
    )
    benchmark_superiority = benchmark.benchmark_superiority_claim_allowed

    blockers: list[str] = []
    if duplicate_domains:
        blockers.append("cyber_school_duplicate_domain_receipt")
    if set(by_domain) != required_domains:
        blockers.append("cyber_school_domain_coverage_incomplete")
    if not curriculum_bound:
        blockers.append("cyber_school_receipt_curriculum_mismatch")
    if receipts and not all(item.defensive_reasoning_ready for item in receipts):
        blockers.append("cyber_school_domain_not_ready")
    if not source_coverage_complete:
        blockers.append("cyber_school_current_source_coverage_incomplete")
    if not architecture_complete:
        blockers.append("cyber_school_architecture_awareness_incomplete")
    if not benchmark_superiority:
        blockers.append("cyber_school_benchmark_superiority_not_proven")
    blockers.extend(benchmark.blockers)
    blockers = list(dict.fromkeys(blockers))

    allowed = not blockers and all(
        (
            domain_coverage_complete,
            source_coverage_complete,
            architecture_complete,
            benchmark_superiority,
        )
    )
    return _seal_model(
        CyberDefenseGraduationDecision,
        {
            "contract": CYBER_DEFENSE_SCHOOL_CONTRACT,
            "curriculum_fingerprint": curriculum.fingerprint,
            "benchmark_profile_fingerprint": benchmark.profile_fingerprint,
            "domain_receipt_fingerprints": tuple(
                item.fingerprint for item in receipts
            ),
            "domain_coverage_complete": domain_coverage_complete,
            "current_source_coverage_complete": source_coverage_complete,
            "architecture_awareness_complete": architecture_complete,
            "benchmark_superiority_proven": benchmark_superiority,
            "mentor_outperformance_claim_allowed": allowed,
            "production_security_superiority_claim_allowed": False,
            "blockers": tuple(blockers),
            "exploit_generation_permitted": False,
            "execution_authority_granted": False,
        },
    )


def _source_policy(source: CyberKnowledgeSource) -> CyberKnowledgeSourcePolicy:
    specs: dict[CyberKnowledgeSource, tuple[CyberSourceAuthority, str, int]] = {
        CyberKnowledgeSource.MITRE_ATTACK: (
            CyberSourceAuthority.ATTACK_BEHAVIOR,
            "source:mitre-attack",
            7 * 24 * 3600,
        ),
        CyberKnowledgeSource.MITRE_D3FEND: (
            CyberSourceAuthority.DEFENSIVE_COUNTERMEASURE,
            "source:mitre-d3fend",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.CISA_KEV: (
            CyberSourceAuthority.KNOWN_EXPLOITATION,
            "source:cisa-kev",
            24 * 3600,
        ),
        CyberKnowledgeSource.FIRST_EPSS: (
            CyberSourceAuthority.EXPLOITATION_PROBABILITY,
            "source:first-epss",
            24 * 3600,
        ),
        CyberKnowledgeSource.NVD_CVE: (
            CyberSourceAuthority.VULNERABILITY_METADATA,
            "source:nvd-cve",
            24 * 3600,
        ),
        CyberKnowledgeSource.CWE: (
            CyberSourceAuthority.WEAKNESS_TAXONOMY,
            "source:mitre-cwe",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.CAPEC: (
            CyberSourceAuthority.ATTACK_PATTERN_TAXONOMY,
            "source:mitre-capec",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.OWASP_ASVS: (
            CyberSourceAuthority.APPLICATION_DEFENSE,
            "source:owasp-asvs",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.OWASP_API: (
            CyberSourceAuthority.APPLICATION_DEFENSE,
            "source:owasp-api-security",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.OWASP_MOBILE: (
            CyberSourceAuthority.APPLICATION_DEFENSE,
            "source:owasp-mobile",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.OWASP_GENAI: (
            CyberSourceAuthority.AI_DEFENSE,
            "source:owasp-genai",
            30 * 24 * 3600,
        ),
        CyberKnowledgeSource.VENDOR_ADVISORY: (
            CyberSourceAuthority.PRODUCT_ADVISORY,
            "source:vendor-advisory",
            24 * 3600,
        ),
        CyberKnowledgeSource.GITHUB_SECURITY_ADVISORY: (
            CyberSourceAuthority.DEPENDENCY_ADVISORY,
            "source:github-security-advisory",
            24 * 3600,
        ),
        CyberKnowledgeSource.SIGMA: (
            CyberSourceAuthority.DETECTION_CONTENT,
            "source:sigma",
            7 * 24 * 3600,
        ),
        CyberKnowledgeSource.YARA: (
            CyberSourceAuthority.DETECTION_CONTENT,
            "source:yara",
            7 * 24 * 3600,
        ),
        CyberKnowledgeSource.NIST_CSF: (
            CyberSourceAuthority.SECURITY_FRAMEWORK,
            "source:nist-csf-2",
            90 * 24 * 3600,
        ),
    }
    authority, source_ref, maximum_age = specs[source]
    return _seal_model(
        CyberKnowledgeSourcePolicy,
        {
            "contract": CYBER_DEFENSE_SCHOOL_CONTRACT,
            "source": source,
            "authority": authority,
            "source_ref": source_ref,
            "server_side_only": True,
            "maximum_observation_age_seconds": maximum_age,
            "can_assert_known_exploitation": source is CyberKnowledgeSource.CISA_KEV,
            "can_assert_company_exposure": False,
            "can_confirm_company_incident": False,
            "attack_instruction_content_allowed": False,
            "exploit_generation_permitted": False,
            "credential_capture_permitted": False,
            "execution_authority_granted": False,
        },
    )


def _required_sources_by_domain() -> dict[
    CyberDefenseDomain,
    tuple[CyberKnowledgeSource, ...],
]:
    source = CyberKnowledgeSource
    return {
        CyberDefenseDomain.WEB_API: (
            source.OWASP_ASVS,
            source.OWASP_API,
            source.CWE,
            source.CAPEC,
            source.MITRE_ATTACK,
            source.CISA_KEV,
            source.NVD_CVE,
        ),
        CyberDefenseDomain.IDENTITY: (
            source.MITRE_ATTACK,
            source.CWE,
            source.CAPEC,
            source.OWASP_ASVS,
            source.MITRE_D3FEND,
        ),
        CyberDefenseDomain.CLOUD_CONTAINER: (
            source.MITRE_ATTACK,
            source.CISA_KEV,
            source.FIRST_EPSS,
            source.NVD_CVE,
            source.VENDOR_ADVISORY,
            source.MITRE_D3FEND,
        ),
        CyberDefenseDomain.ENDPOINT_NETWORK: (
            source.MITRE_ATTACK,
            source.CISA_KEV,
            source.FIRST_EPSS,
            source.NVD_CVE,
            source.SIGMA,
            source.YARA,
            source.MITRE_D3FEND,
        ),
        CyberDefenseDomain.SOFTWARE_SUPPLY_CHAIN: (
            source.CISA_KEV,
            source.NVD_CVE,
            source.GITHUB_SECURITY_ADVISORY,
            source.VENDOR_ADVISORY,
            source.CWE,
        ),
        CyberDefenseDomain.DATA_SECURITY: (
            source.OWASP_ASVS,
            source.OWASP_API,
            source.CWE,
            source.CAPEC,
            source.MITRE_ATTACK,
        ),
        CyberDefenseDomain.MOBILE_DEVICE: (
            source.OWASP_MOBILE,
            source.MITRE_ATTACK,
            source.CWE,
            source.VENDOR_ADVISORY,
        ),
        CyberDefenseDomain.AI_AGENTIC: (
            source.OWASP_GENAI,
            source.CWE,
            source.CAPEC,
            source.VENDOR_ADVISORY,
            source.NIST_CSF,
        ),
        CyberDefenseDomain.INSIDER_SOCIAL: (
            source.MITRE_ATTACK,
            source.SIGMA,
            source.MITRE_D3FEND,
            source.NIST_CSF,
        ),
        CyberDefenseDomain.IOT_OT: (
            source.MITRE_ATTACK,
            source.CISA_KEV,
            source.NVD_CVE,
            source.VENDOR_ADVISORY,
            source.MITRE_D3FEND,
        ),
        CyberDefenseDomain.INCIDENT_RESPONSE_DETECTION: (
            source.MITRE_ATTACK,
            source.SIGMA,
            source.YARA,
            source.MITRE_D3FEND,
            source.CISA_KEV,
            source.NIST_CSF,
        ),
    }


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _seal_model(model_type: type[_ModelT], values: dict[str, Any]) -> _ModelT:
    """Seal using Pydantic's canonical JSON representation.

    This prevents equivalent timezone-aware datetimes such as ``+00:00`` and
    ``Z`` from producing different fingerprints between construction and
    validation.
    """

    constructed = model_type.model_construct(**values, fingerprint="0" * 64)
    payload = constructed.model_dump(mode="json", exclude={"fingerprint"})
    return model_type.model_validate(
        {**payload, "fingerprint": _fingerprint(payload)}
    )


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={"fingerprint"})


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    _aware(value, "cyber_school_datetime_requires_timezone")
    return value.isoformat()
