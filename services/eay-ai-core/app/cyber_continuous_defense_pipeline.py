"""Continuous defensive cyber pipeline for EAY Jarvis.

This module composes the existing canonical cyber authorities instead of creating
parallel truth planes. Public threat feeds remain global. EAY exposure, detection
coverage and incident state remain exact-company evidence. Every response is
advisory; no exploit generation, credential capture, automatic remediation or
production mutation is represented here.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.company_cyber_incident_intelligence import (
    CompanyIncidentAssessment,
    CompanySecuritySignal,
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    assess_company_incident,
    build_company_security_signal,
)
from app.cyber_attack_path_intelligence import (
    BlastRadiusAssessment,
    CompanyAttackGraphSnapshot,
    CyberRelationKind,
    CyberSurfaceKind,
    DefensiveAttackPathSet,
    RelationEvidenceStrength,
    assess_blast_radius,
    build_company_attack_graph_snapshot,
    build_company_cyber_node,
    build_company_cyber_relation,
    enumerate_defensive_attack_paths,
)
from app.cyber_benchmark_intelligence import (
    CyberBenchmarkComparison,
    CyberBenchmarkEvidenceClass,
    CyberBenchmarkProfile,
    build_cyber_benchmark_run,
    compare_cyber_benchmark_runs,
)
from app.cyber_defense_intelligence import (
    AssetCriticality,
    CompanyCyberExposure,
    DefensiveAction,
    DefensiveResponseCandidate,
    ExposureStatus,
    PatchStatus,
    ThreatIntelligenceSource,
    ThreatKnowledgeRecord,
    build_company_exposure,
    build_defensive_response_candidate,
    build_threat_record,
)
from app.cyber_defense_priority_intelligence import (
    CompanyExposureClaim,
    DefensivePriorityReceipt,
    build_defensive_priority_receipt,
)
from app.cyber_threat_enrichment_intelligence import EpssObservation, build_epss_observation
from app.jarvis_benchmark import BenchmarkRun, MetricMeasurement

CYBER_CONTINUOUS_DEFENSE_CONTRACT = "eay-cyber-continuous-defense-v1"
_MAX_FEED_BYTES = 4 * 1024 * 1024
_CVE = re.compile(r"^CVE-\d{4}-\d{4,19}$", re.IGNORECASE)
_CWE = re.compile(r"^CWE-\d+$", re.IGNORECASE)
_ATTACK = re.compile(r"^T\d{4}(?:\.\d{3})?$", re.IGNORECASE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)

CISA_KEV_CANONICAL_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
CISA_KEV_OFFICIAL_MIRROR_URL = (
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/"
    "known_exploited_vulnerabilities.json"
)
NVD_CVE_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
FIRST_EPSS_API_URL = "https://api.first.org/data/v1/epss"
_ALLOWED_ENDPOINTS = {
    CISA_KEV_CANONICAL_URL,
    CISA_KEV_OFFICIAL_MIRROR_URL,
    NVD_CVE_API_URL,
    FIRST_EPSS_API_URL,
}


class LiveThreatFeedSource(str, Enum):
    CISA_KEV = "cisa_kev"
    NVD_CVE = "nvd_cve"
    FIRST_EPSS = "first_epss"


class FeedTransport(str, Enum):
    CANONICAL = "canonical"
    OFFICIAL_MIRROR = "official_mirror"


class FeedObservationStatus(str, Enum):
    CURRENT = "current"
    MIRROR_CURRENT = "mirror_current"
    UNAVAILABLE = "unavailable"


class LiveThreatSourceUnavailable(RuntimeError):
    """Public source could not be observed without weakening the source policy."""


class PublicFeedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    source: LiveThreatFeedSource
    transport: FeedTransport
    status: FeedObservationStatus
    endpoint_ref: str = Field(min_length=1)
    observed_at: datetime
    http_status: int = Field(ge=100, le=599)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_authority_observed: bool
    evidence_ref: str = Field(min_length=1)
    credentials_sent: bool = False
    arbitrary_url_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_public_and_bounded(self) -> PublicFeedObservation:
        _aware(self.observed_at, "cyber_live_feed_observed_at_requires_timezone")
        if self.credentials_sent or self.arbitrary_url_allowed:
            raise ValueError("cyber_live_feed_unbounded_network_or_credentials_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_live_feed_never_grants_execution_authority")
        _safe_ref(self.endpoint_ref, "cyber_live_feed_unsafe_endpoint_ref")
        _safe_ref(self.evidence_ref, "cyber_live_feed_unsafe_evidence_ref")
        _verify(self, "cyber_live_feed_fingerprint_mismatch")
        return self


class LiveThreatIngestionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    cve_id: str
    as_of: datetime
    primary_threat: ThreatKnowledgeRecord
    nvd_threat: ThreatKnowledgeRecord | None = None
    kev_threat: ThreatKnowledgeRecord | None = None
    epss: EpssObservation | None = None
    nvd_cpe_refs: tuple[str, ...] = ()
    vendor_product_refs: tuple[str, ...] = ()
    source_observations: tuple[PublicFeedObservation, ...] = Field(min_length=1)
    known_exploitation_authority_observed: bool
    current_nvd_observed: bool
    current_epss_observed: bool
    company_truth_granted: bool = False
    incident_confirmation_granted: bool = False
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ingestion_is_global_not_company_truth(self) -> LiveThreatIngestionReceipt:
        _cve(self.cve_id)
        _aware(self.as_of, "cyber_live_ingestion_as_of_requires_timezone")
        ThreatKnowledgeRecord.model_validate(self.primary_threat.model_dump(mode="json"))
        if self.primary_threat.known_exploited_in_wild:
            if self.primary_threat.source is not ThreatIntelligenceSource.CISA_KEV:
                raise ValueError("cyber_live_known_exploitation_requires_cisa_kev")
            if not self.known_exploitation_authority_observed:
                raise ValueError("cyber_live_known_exploitation_requires_authority_observation")
        if self.company_truth_granted or self.incident_confirmation_granted:
            raise ValueError("cyber_live_public_sources_never_grant_company_truth")
        if self.exploit_generation_permitted or self.execution_authority_granted:
            raise ValueError("cyber_live_ingestion_never_grants_offensive_authority")
        _unique(self.nvd_cpe_refs, "cyber_live_cpe_refs_must_be_unique")
        _unique(self.vendor_product_refs, "cyber_live_product_refs_must_be_unique")
        _verify(self, "cyber_live_ingestion_fingerprint_mismatch")
        return self


class EayAssetObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    asset_ref: str = Field(min_length=1)
    surface_kind: CyberSurfaceKind
    criticality: AssetCriticality
    product_refs: tuple[str, ...] = ()
    cpe_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    deployment_observed: bool = False
    internet_reachable: bool = False
    privileged: bool = False
    crown_jewel: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def asset_is_evidenced_and_company_neutral(self) -> EayAssetObservation:
        _aware(self.observed_at, "eay_asset_observed_at_requires_timezone")
        _aware(self.recorded_at, "eay_asset_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("eay_asset_recorded_before_observed")
        if self.execution_authority_granted:
            raise ValueError("eay_asset_observation_never_grants_execution_authority")
        for values in (self.product_refs, self.cpe_refs, self.evidence_refs):
            _unique(values, "eay_asset_refs_must_be_unique")
            for ref in values:
                _safe_ref(ref, "eay_asset_unsafe_ref")
        _safe_ref(self.asset_ref, "eay_asset_unsafe_ref")
        _verify(self, "eay_asset_observation_fingerprint_mismatch")
        return self


class EayDependencyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    relation_id: str = Field(min_length=1)
    from_asset_ref: str = Field(min_length=1)
    to_asset_ref: str = Field(min_length=1)
    relation_kind: CyberRelationKind = CyberRelationKind.DEPENDENCY
    evidence_strength: RelationEvidenceStrength = RelationEvidenceStrength.VERIFIED_CONFIGURATION
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    attack_technique_ids: tuple[str, ...] = ()
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def dependency_is_evidence_only(self) -> EayDependencyObservation:
        _aware(self.observed_at, "eay_dependency_observed_at_requires_timezone")
        _aware(self.recorded_at, "eay_dependency_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("eay_dependency_recorded_before_observed")
        if self.from_asset_ref == self.to_asset_ref:
            raise ValueError("eay_dependency_self_loop_forbidden")
        if self.execution_authority_granted:
            raise ValueError("eay_dependency_never_grants_execution_authority")
        _unique(self.evidence_refs, "eay_dependency_evidence_refs_must_be_unique")
        _unique(self.attack_technique_ids, "eay_dependency_attack_ids_must_be_unique")
        for technique_id in self.attack_technique_ids:
            if not _ATTACK.fullmatch(technique_id):
                raise ValueError("eay_dependency_invalid_attack_technique")
        for ref in (
            self.relation_id,
            self.from_asset_ref,
            self.to_asset_ref,
            *self.evidence_refs,
        ):
            _safe_ref(ref, "eay_dependency_unsafe_ref")
        _verify(self, "eay_dependency_fingerprint_mismatch")
        return self


class EayAssetInventorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    identity: CompanyIdentity
    as_of: datetime
    assets: tuple[EayAssetObservation, ...]
    dependencies: tuple[EayDependencyObservation, ...]
    inventory_coverage_complete: bool = False
    production_deployment_truth_claimed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def inventory_does_not_overclaim_repository_evidence(self) -> EayAssetInventorySnapshot:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.as_of, "eay_inventory_as_of_requires_timezone")
        asset_refs = [asset.asset_ref for asset in self.assets]
        if len(asset_refs) != len(set(asset_refs)):
            raise ValueError("eay_inventory_duplicate_asset")
        asset_set = set(asset_refs)
        relation_ids: set[str] = set()
        for dependency in self.dependencies:
            if dependency.relation_id in relation_ids:
                raise ValueError("eay_inventory_duplicate_dependency")
            relation_ids.add(dependency.relation_id)
            if dependency.from_asset_ref not in asset_set or dependency.to_asset_ref not in asset_set:
                raise ValueError("eay_inventory_dependency_endpoint_missing")
        if self.production_deployment_truth_claimed and not all(
            asset.deployment_observed for asset in self.assets
        ):
            raise ValueError("eay_inventory_production_truth_requires_deployment_evidence")
        if self.execution_authority_granted:
            raise ValueError("eay_inventory_never_grants_execution_authority")
        _verify(self, "eay_inventory_fingerprint_mismatch")
        return self


class CveAssetMatchStatus(str, Enum):
    POTENTIAL = "potential"
    CONFIRMED = "confirmed"


class CveAssetMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_ref: str
    status: CveAssetMatchStatus
    matched_refs: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    exact_version_or_cpe_match: bool
    deployment_observed: bool


class EayCveImpactStatus(str, Enum):
    UNKNOWN = "unknown"
    NO_MATCH_OBSERVED = "no_match_observed"
    POTENTIAL = "potential"
    CONFIRMED = "confirmed"


class EayCveImpactReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    identity: CompanyIdentity
    cve_id: str
    as_of: datetime
    threat_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: EayCveImpactStatus
    matches: tuple[CveAssetMatch, ...]
    exposures: tuple[CompanyCyberExposure, ...]
    priorities: tuple[DefensivePriorityReceipt, ...]
    firm_company_impact_authorized: bool
    no_match_is_not_proof_of_safety: bool = True
    reason_codes: tuple[str, ...] = Field(min_length=1)
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def impact_requires_exact_company_evidence(self) -> EayCveImpactReceipt:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _cve(self.cve_id)
        _aware(self.as_of, "eay_cve_impact_as_of_requires_timezone")
        if self.firm_company_impact_authorized:
            if self.status is not EayCveImpactStatus.CONFIRMED:
                raise ValueError("eay_cve_firm_impact_requires_confirmed_status")
            if not any(
                priority.exposure_claim is CompanyExposureClaim.AFFECTED
                and priority.firm_company_exposure_claim_authorized
                for priority in self.priorities
            ):
                raise ValueError("eay_cve_firm_impact_requires_canonical_priority_proof")
        if not self.no_match_is_not_proof_of_safety:
            raise ValueError("eay_cve_no_match_cannot_become_safety_proof")
        if self.execution_authority_granted:
            raise ValueError("eay_cve_impact_never_grants_execution_authority")
        _unique(self.reason_codes, "eay_cve_impact_reasons_must_be_unique")
        _verify(self, "eay_cve_impact_fingerprint_mismatch")
        return self


class EayAttackGraphReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: CompanyAttackGraphSnapshot
    path_set: DefensiveAttackPathSet | None = None
    blast_radius: BlastRadiusAssessment | None = None
    affected_entry_refs: tuple[str, ...] = ()
    attack_success_proven: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def graph_receipt_is_advisory(self) -> EayAttackGraphReceipt:
        if self.attack_success_proven or self.incident_confirmation_granted:
            raise ValueError("eay_attack_graph_never_confirms_attack_or_incident")
        if self.execution_authority_granted:
            raise ValueError("eay_attack_graph_never_grants_execution_authority")
        _unique(self.affected_entry_refs, "eay_attack_graph_entries_must_be_unique")
        _verify(self, "eay_attack_graph_receipt_fingerprint_mismatch")
        return self


class SigmaRuleMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    rule_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)
    level: str | None = None
    logsource_category: str | None = None
    logsource_product: str | None = None
    logsource_service: str | None = None
    tags: tuple[str, ...] = ()
    attack_technique_ids: tuple[str, ...] = ()
    cve_ids: tuple[str, ...] = ()
    evidence_ref: str = Field(min_length=1)
    detection_body_ingested: bool = False
    automatic_deployment_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def sigma_is_metadata_only(self) -> SigmaRuleMetadata:
        if self.detection_body_ingested:
            raise ValueError("sigma_pipeline_ingests_metadata_not_detection_payload")
        if self.automatic_deployment_permitted or self.execution_authority_granted:
            raise ValueError("sigma_pipeline_never_auto_deploys")
        _unique(self.tags, "sigma_tags_must_be_unique")
        _unique(self.attack_technique_ids, "sigma_attack_ids_must_be_unique")
        _unique(self.cve_ids, "sigma_cve_ids_must_be_unique")
        for technique in self.attack_technique_ids:
            if not _ATTACK.fullmatch(technique):
                raise ValueError("sigma_invalid_attack_technique")
        for cve_id in self.cve_ids:
            _cve(cve_id)
        _safe_ref(self.rule_id, "sigma_unsafe_rule_ref")
        _safe_ref(self.evidence_ref, "sigma_unsafe_evidence_ref")
        _verify(self, "sigma_rule_metadata_fingerprint_mismatch")
        return self

    @property
    def logsource_key(self) -> str:
        values = (
            self.logsource_category or "-",
            self.logsource_product or "-",
            self.logsource_service or "-",
        )
        return "sigma-logsource:" + "/".join(value.lower() for value in values)


class SigmaTelemetryStatus(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    MISSING = "missing"


class SigmaTelemetryObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    identity: CompanyIdentity
    logsource_key: str = Field(min_length=1)
    status: SigmaTelemetryStatus
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    telemetry_ref: str | None = None
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def telemetry_is_company_evidence(self) -> SigmaTelemetryObservation:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.observed_at, "sigma_telemetry_observed_at_requires_timezone")
        _aware(self.recorded_at, "sigma_telemetry_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("sigma_telemetry_recorded_before_observed")
        if self.status in {SigmaTelemetryStatus.AVAILABLE, SigmaTelemetryStatus.DEGRADED}:
            if self.telemetry_ref is None:
                raise ValueError("sigma_live_telemetry_requires_ref")
        elif self.telemetry_ref is not None:
            raise ValueError("sigma_missing_telemetry_cannot_claim_ref")
        if self.execution_authority_granted:
            raise ValueError("sigma_telemetry_never_grants_execution_authority")
        _verify(self, "sigma_telemetry_fingerprint_mismatch")
        return self


class SigmaCoverageStatus(str, Enum):
    NO_RELEVANT_RULE = "no_relevant_rule"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    COVERED = "covered"


class SigmaCoverageReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    identity: CompanyIdentity
    cve_id: str
    as_of: datetime
    relevant_rule_ids: tuple[str, ...]
    covered_rule_ids: tuple[str, ...]
    degraded_rule_ids: tuple[str, ...]
    missing_rule_ids: tuple[str, ...]
    unverified_rule_ids: tuple[str, ...]
    status: SigmaCoverageStatus
    firm_detection_gap_authorized: bool
    automatic_rule_deployment_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def sigma_coverage_does_not_turn_unknown_into_gap(self) -> SigmaCoverageReceipt:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _cve(self.cve_id)
        _aware(self.as_of, "sigma_coverage_as_of_requires_timezone")
        if self.firm_detection_gap_authorized and self.unverified_rule_ids:
            raise ValueError("sigma_firm_gap_requires_complete_current_evidence")
        if self.automatic_rule_deployment_permitted or self.execution_authority_granted:
            raise ValueError("sigma_coverage_never_grants_deployment_or_execution")
        for values in (
            self.relevant_rule_ids,
            self.covered_rule_ids,
            self.degraded_rule_ids,
            self.missing_rule_ids,
            self.unverified_rule_ids,
        ):
            _unique(values, "sigma_coverage_rule_sets_must_be_unique")
        _verify(self, "sigma_coverage_fingerprint_mismatch")
        return self


class SandboxEvidenceClass(str, Enum):
    REPOSITORY_ISOLATED = "repository_isolated"
    AUTHORIZED_EXTERNAL = "authorized_external"


class SandboxCheck(BaseModel):
    check_id: str
    passed: bool
    evidence_ref: str


class ControlledSandboxValidationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    identity: CompanyIdentity
    environment: SandboxEvidenceClass
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_evidence_ref: str | None = None
    checks: tuple[SandboxCheck, ...] = Field(min_length=1)
    passed: bool
    qualifies_as_authorized_sandbox_benchmark_evidence: bool
    destructive_actions_allowed: bool = False
    exploit_generation_allowed: bool = False
    credential_capture_allowed: bool = False
    production_write_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def sandbox_is_non_destructive(self) -> ControlledSandboxValidationReceipt:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if self.environment is SandboxEvidenceClass.AUTHORIZED_EXTERNAL:
            if not self.authorization_evidence_ref:
                raise ValueError("cyber_sandbox_external_requires_authorization_evidence")
        elif self.qualifies_as_authorized_sandbox_benchmark_evidence:
            raise ValueError("repository_isolated_sandbox_is_not_strong_benchmark_evidence")
        expected_pass = all(check.passed for check in self.checks)
        if self.passed != expected_pass:
            raise ValueError("cyber_sandbox_pass_mismatch")
        expected_qualifies = (
            self.passed
            and self.environment is SandboxEvidenceClass.AUTHORIZED_EXTERNAL
            and bool(self.authorization_evidence_ref)
        )
        if self.qualifies_as_authorized_sandbox_benchmark_evidence != expected_qualifies:
            raise ValueError("cyber_sandbox_evidence_class_mismatch")
        if (
            self.destructive_actions_allowed
            or self.exploit_generation_allowed
            or self.credential_capture_allowed
            or self.production_write_allowed
            or self.execution_authority_granted
        ):
            raise ValueError("cyber_sandbox_offensive_or_write_authority_forbidden")
        _verify(self, "cyber_sandbox_fingerprint_mismatch")
        return self


class ContinuousCyberBenchmarkCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    revision_ref: str = Field(min_length=1)
    profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_class: CyberBenchmarkEvidenceClass
    run: BenchmarkRun
    comparison: CyberBenchmarkComparison | None = None
    benchmark_superiority_claim_allowed: bool
    production_security_superiority_claim_allowed: bool = False
    automatic_promotion_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def checkpoint_cannot_self_promote(self) -> ContinuousCyberBenchmarkCheckpoint:
        if self.production_security_superiority_claim_allowed:
            raise ValueError("continuous_cyber_benchmark_never_proves_production_superiority")
        if self.automatic_promotion_allowed or self.execution_authority_granted:
            raise ValueError("continuous_cyber_benchmark_never_self_promotes")
        allowed = bool(
            self.comparison is not None
            and self.comparison.benchmark_superiority_claim_allowed
        )
        if self.benchmark_superiority_claim_allowed != allowed:
            raise ValueError("continuous_cyber_benchmark_claim_mismatch")
        _safe_ref(self.revision_ref, "continuous_cyber_benchmark_unsafe_revision")
        _verify(self, "continuous_cyber_benchmark_fingerprint_mismatch")
        return self


class ContinuousDefenseCycleReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CONTINUOUS_DEFENSE_CONTRACT
    identity: CompanyIdentity
    threat: LiveThreatIngestionReceipt
    impact: EayCveImpactReceipt
    graph: EayAttackGraphReceipt
    sigma: SigmaCoverageReceipt
    incident: CompanyIncidentAssessment | None
    recommendations: tuple[DefensiveResponseCandidate, ...]
    sandbox: ControlledSandboxValidationReceipt
    benchmark: ContinuousCyberBenchmarkCheckpoint | None = None
    automatic_remediation_permitted: bool = False
    production_write_permitted: bool = False
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def cycle_remains_defensive(self) -> ContinuousDefenseCycleReceipt:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if (
            self.automatic_remediation_permitted
            or self.production_write_permitted
            or self.exploit_generation_permitted
            or self.execution_authority_granted
        ):
            raise ValueError("continuous_cyber_cycle_never_grants_write_or_offensive_authority")
        _verify(self, "continuous_cyber_cycle_fingerprint_mismatch")
        return self


class LiveThreatFeedClient:
    """Allowlisted, credential-free public threat feed reader."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "EAY-Jarvis-CyberDefense/1.0",
            },
        )

    def close(self) -> None:
        self._client.close()

    def fetch_kev_catalog(self, *, observed_at: datetime) -> tuple[dict[str, Any], PublicFeedObservation]:
        _aware(observed_at, "cyber_live_kev_observed_at_requires_timezone")
        try:
            payload, status, digest = self._get_json(CISA_KEV_CANONICAL_URL)
            observation = _feed_observation(
                source=LiveThreatFeedSource.CISA_KEV,
                transport=FeedTransport.CANONICAL,
                status=FeedObservationStatus.CURRENT,
                endpoint_ref="cisa-kev:canonical-json",
                observed_at=observed_at,
                http_status=status,
                content_sha256=digest,
                canonical_authority_observed=True,
            )
            return payload, observation
        except LiveThreatSourceUnavailable:
            payload, status, digest = self._get_json(CISA_KEV_OFFICIAL_MIRROR_URL)
            observation = _feed_observation(
                source=LiveThreatFeedSource.CISA_KEV,
                transport=FeedTransport.OFFICIAL_MIRROR,
                status=FeedObservationStatus.MIRROR_CURRENT,
                endpoint_ref="cisagov-kev-data:official-mirror-json",
                observed_at=observed_at,
                http_status=status,
                content_sha256=digest,
                canonical_authority_observed=False,
            )
            return payload, observation

    def fetch_nvd_cve(
        self,
        *,
        cve_id: str,
        observed_at: datetime,
    ) -> tuple[dict[str, Any], PublicFeedObservation]:
        _cve(cve_id)
        payload, status, digest = self._get_json(NVD_CVE_API_URL, params={"cveId": cve_id})
        observation = _feed_observation(
            source=LiveThreatFeedSource.NVD_CVE,
            transport=FeedTransport.CANONICAL,
            status=FeedObservationStatus.CURRENT,
            endpoint_ref="nvd:cve-api-2.0",
            observed_at=observed_at,
            http_status=status,
            content_sha256=digest,
            canonical_authority_observed=True,
        )
        return payload, observation

    def fetch_epss(
        self,
        *,
        cve_id: str,
        observed_at: datetime,
    ) -> tuple[dict[str, Any], PublicFeedObservation]:
        _cve(cve_id)
        payload, status, digest = self._get_json(FIRST_EPSS_API_URL, params={"cve": cve_id})
        observation = _feed_observation(
            source=LiveThreatFeedSource.FIRST_EPSS,
            transport=FeedTransport.CANONICAL,
            status=FeedObservationStatus.CURRENT,
            endpoint_ref="first:epss-api-v1",
            observed_at=observed_at,
            http_status=status,
            content_sha256=digest,
            canonical_authority_observed=True,
        )
        return payload, observation

    def _get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> tuple[dict[str, Any], int, str]:
        _validate_public_endpoint(url)
        if params:
            allowed = {"cveId", "cveIds", "cve"}
            if set(params) - allowed:
                raise ValueError("cyber_live_feed_unapproved_query_parameter")
            for value in params.values():
                if not _CVE.fullmatch(value):
                    raise ValueError("cyber_live_feed_query_must_be_exact_cve")
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise LiveThreatSourceUnavailable("cyber_live_feed_network_unavailable") from exc
        if response.status_code != 200:
            raise LiveThreatSourceUnavailable(
                f"cyber_live_feed_http_unavailable:{response.status_code}"
            )
        content = response.content
        if len(content) > _MAX_FEED_BYTES:
            raise LiveThreatSourceUnavailable("cyber_live_feed_response_too_large")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LiveThreatSourceUnavailable("cyber_live_feed_invalid_json") from exc
        if not isinstance(payload, dict):
            raise LiveThreatSourceUnavailable("cyber_live_feed_json_object_required")
        return payload, response.status_code, hashlib.sha256(content).hexdigest()


def ingest_live_public_threat(
    *,
    client: LiveThreatFeedClient,
    cve_id: str,
    as_of: datetime,
) -> LiveThreatIngestionReceipt:
    """Read public sources and construct canonical global threat evidence."""

    _cve(cve_id)
    _aware(as_of, "cyber_live_ingestion_as_of_requires_timezone")
    observations: list[PublicFeedObservation] = []

    nvd_payload, nvd_observation = client.fetch_nvd_cve(cve_id=cve_id, observed_at=as_of)
    observations.append(nvd_observation)
    nvd_item = _extract_nvd_cve(nvd_payload, cve_id)
    published_at = _parse_datetime(nvd_item.get("published"))
    cwe_ids = _extract_nvd_cwes(nvd_item)
    cpe_refs = _extract_nvd_cpes(nvd_item)
    severity = _extract_nvd_severity(nvd_item)
    nvd_threat = build_threat_record(
        record_id=f"threat:nvd:{cve_id}",
        source=ThreatIntelligenceSource.NVD,
        source_record_id=cve_id,
        published_at=published_at,
        recorded_at=as_of,
        source_evidence_ref=f"nvd-cve:{cve_id}:{nvd_observation.content_sha256[:16]}",
        product_refs=cpe_refs,
        cve_ids=(cve_id,),
        cwe_ids=cwe_ids,
        severity_score=severity,
    )

    kev_threat: ThreatKnowledgeRecord | None = None
    vendor_product_refs: tuple[str, ...] = ()
    known_authority_observed = False
    try:
        kev_payload, kev_observation = client.fetch_kev_catalog(observed_at=as_of)
        observations.append(kev_observation)
        kev_entry = _find_kev_entry(kev_payload, cve_id)
        if kev_entry is not None:
            vendor_product_refs = (
                _vendor_product_ref(kev_entry.get("vendorProject"), kev_entry.get("product")),
            )
            kev_cwes = tuple(
                value.upper()
                for value in kev_entry.get("cwes", [])
                if isinstance(value, str) and _CWE.fullmatch(value)
            )
            date_added = _parse_date_as_datetime(kev_entry.get("dateAdded"))
            kev_threat = build_threat_record(
                record_id=f"threat:cisa-kev:{cve_id}",
                source=ThreatIntelligenceSource.CISA_KEV,
                source_record_id=cve_id,
                published_at=date_added,
                recorded_at=as_of,
                source_evidence_ref=(
                    f"cisa-kev:{cve_id}:{kev_observation.content_sha256[:16]}"
                ),
                product_refs=vendor_product_refs,
                cve_ids=(cve_id,),
                cwe_ids=kev_cwes,
                severity_score=severity,
                known_exploited_in_wild=True,
            )
            # CISA's official GitHub mirror is still CISA-produced KEV data; the
            # transport distinction is retained so freshness can never be
            # misrepresented as a direct canonical cisa.gov observation.
            known_authority_observed = kev_observation.transport in {
                FeedTransport.CANONICAL,
                FeedTransport.OFFICIAL_MIRROR,
            }
    except LiveThreatSourceUnavailable:
        pass

    epss: EpssObservation | None = None
    current_epss = False
    try:
        epss_payload, epss_observation = client.fetch_epss(cve_id=cve_id, observed_at=as_of)
        observations.append(epss_observation)
        epss_item = _extract_epss_item(epss_payload, cve_id)
        if epss_item is not None:
            score_date = date.fromisoformat(str(epss_item.get("date")))
            epss = build_epss_observation(
                cve_id=cve_id,
                score=float(epss_item["epss"]),
                percentile=float(epss_item["percentile"]),
                score_date=score_date,
                observed_at=as_of,
                recorded_at=as_of,
                source_evidence_ref=(
                    f"first-epss:{cve_id}:{epss_observation.content_sha256[:16]}"
                ),
            )
            current_epss = score_date <= as_of.date()
    except (LiveThreatSourceUnavailable, KeyError, TypeError, ValueError):
        pass

    primary = kev_threat or nvd_threat
    draft = {
        "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
        "cve_id": cve_id,
        "as_of": as_of,
        "primary_threat": primary,
        "nvd_threat": nvd_threat,
        "kev_threat": kev_threat,
        "epss": epss,
        "nvd_cpe_refs": cpe_refs,
        "vendor_product_refs": vendor_product_refs,
        "source_observations": tuple(observations),
        "known_exploitation_authority_observed": known_authority_observed,
        "current_nvd_observed": True,
        "current_epss_observed": current_epss,
        "company_truth_granted": False,
        "incident_confirmation_granted": False,
        "exploit_generation_permitted": False,
        "execution_authority_granted": False,
    }
    return _seal(LiveThreatIngestionReceipt, draft)


def build_asset_inventory_snapshot(
    *,
    identity: CompanyIdentity,
    assets: tuple[EayAssetObservation, ...],
    dependencies: tuple[EayDependencyObservation, ...],
    as_of: datetime,
    inventory_coverage_complete: bool = False,
    production_deployment_truth_claimed: bool = False,
) -> EayAssetInventorySnapshot:
    draft = {
        "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
        "identity": identity,
        "as_of": as_of,
        "assets": assets,
        "dependencies": dependencies,
        "inventory_coverage_complete": inventory_coverage_complete,
        "production_deployment_truth_claimed": production_deployment_truth_claimed,
        "execution_authority_granted": False,
    }
    return _seal(EayAssetInventorySnapshot, draft)


def build_asset_observation(
    *,
    asset_ref: str,
    surface_kind: CyberSurfaceKind,
    criticality: AssetCriticality,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    product_refs: tuple[str, ...] = (),
    cpe_refs: tuple[str, ...] = (),
    deployment_observed: bool = False,
    internet_reachable: bool = False,
    privileged: bool = False,
    crown_jewel: bool = False,
) -> EayAssetObservation:
    return _seal(
        EayAssetObservation,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "asset_ref": asset_ref,
            "surface_kind": surface_kind,
            "criticality": criticality,
            "product_refs": product_refs,
            "cpe_refs": cpe_refs,
            "evidence_refs": evidence_refs,
            "observed_at": observed_at,
            "recorded_at": recorded_at,
            "deployment_observed": deployment_observed,
            "internet_reachable": internet_reachable,
            "privileged": privileged,
            "crown_jewel": crown_jewel,
            "execution_authority_granted": False,
        },
    )


def build_dependency_observation(
    *,
    relation_id: str,
    from_asset_ref: str,
    to_asset_ref: str,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    relation_kind: CyberRelationKind = CyberRelationKind.DEPENDENCY,
    evidence_strength: RelationEvidenceStrength = RelationEvidenceStrength.VERIFIED_CONFIGURATION,
    attack_technique_ids: tuple[str, ...] = (),
) -> EayDependencyObservation:
    return _seal(
        EayDependencyObservation,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "relation_id": relation_id,
            "from_asset_ref": from_asset_ref,
            "to_asset_ref": to_asset_ref,
            "relation_kind": relation_kind,
            "evidence_strength": evidence_strength,
            "evidence_refs": evidence_refs,
            "observed_at": observed_at,
            "recorded_at": recorded_at,
            "attack_technique_ids": attack_technique_ids,
            "execution_authority_granted": False,
        },
    )


def materialize_eay_attack_graph(
    *,
    inventory: EayAssetInventorySnapshot,
    affected_entry_refs: tuple[str, ...] = (),
) -> EayAttackGraphReceipt:
    inventory = EayAssetInventorySnapshot.model_validate(inventory.model_dump(mode="json"))
    nodes = tuple(
        build_company_cyber_node(
            identity=inventory.identity,
            node_ref=asset.asset_ref,
            surface_kind=asset.surface_kind,
            criticality=asset.criticality,
            evidence_refs=asset.evidence_refs,
            observed_at=asset.observed_at,
            recorded_at=asset.recorded_at,
            internet_reachable=asset.internet_reachable,
            privileged=asset.privileged,
            crown_jewel=asset.crown_jewel,
        )
        for asset in inventory.assets
    )
    relations = tuple(
        build_company_cyber_relation(
            identity=inventory.identity,
            relation_id=dependency.relation_id,
            from_node_ref=dependency.from_asset_ref,
            to_node_ref=dependency.to_asset_ref,
            relation_kind=dependency.relation_kind,
            evidence_strength=dependency.evidence_strength,
            evidence_refs=dependency.evidence_refs,
            observed_at=dependency.observed_at,
            recorded_at=dependency.recorded_at,
            attack_technique_ids=dependency.attack_technique_ids,
        )
        for dependency in inventory.dependencies
    )
    snapshot = build_company_attack_graph_snapshot(
        identity=inventory.identity,
        nodes=nodes,
        relations=relations,
        as_of=inventory.as_of,
    )
    eligible_entries = tuple(
        sorted(ref for ref in set(affected_entry_refs) if ref in {n.node_ref for n in nodes})
    )
    path_set: DefensiveAttackPathSet | None = None
    blast: BlastRadiusAssessment | None = None
    if eligible_entries:
        path_set = enumerate_defensive_attack_paths(
            snapshot=snapshot,
            entry_node_refs=eligible_entries,
        )
        blast = assess_blast_radius(snapshot=snapshot, path_set=path_set)
    return _seal(
        EayAttackGraphReceipt,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "inventory_fingerprint": inventory.fingerprint,
            "snapshot": snapshot,
            "path_set": path_set,
            "blast_radius": blast,
            "affected_entry_refs": eligible_entries,
            "attack_success_proven": False,
            "incident_confirmation_granted": False,
            "execution_authority_granted": False,
        },
    )


def assess_eay_cve_impact(
    *,
    ingestion: LiveThreatIngestionReceipt,
    inventory: EayAssetInventorySnapshot,
    as_of: datetime,
    max_company_evidence_age_seconds: int = 86400,
) -> EayCveImpactReceipt:
    ingestion = LiveThreatIngestionReceipt.model_validate(ingestion.model_dump(mode="json"))
    inventory = EayAssetInventorySnapshot.model_validate(inventory.model_dump(mode="json"))
    _same_identity(inventory.identity, inventory.identity)
    if max_company_evidence_age_seconds <= 0:
        raise ValueError("eay_cve_company_evidence_age_must_be_positive")

    threat_refs = set(ingestion.nvd_cpe_refs)
    product_refs = set(ingestion.vendor_product_refs)
    matches: list[CveAssetMatch] = []
    exposures: list[CompanyCyberExposure] = []
    priorities: list[DefensivePriorityReceipt] = []

    for asset in inventory.assets:
        exact_cpes = tuple(sorted(set(asset.cpe_refs) & threat_refs))
        exact_products = tuple(sorted(set(asset.product_refs) & product_refs))
        if not exact_cpes and not exact_products:
            continue
        confirmed = bool(exact_cpes and asset.deployment_observed)
        match_status = CveAssetMatchStatus.CONFIRMED if confirmed else CveAssetMatchStatus.POTENTIAL
        matched_refs = exact_cpes or exact_products
        evidence_refs = tuple(dict.fromkeys((*asset.evidence_refs, f"threat:{ingestion.fingerprint[:24]}")))
        matches.append(
            CveAssetMatch(
                asset_ref=asset.asset_ref,
                status=match_status,
                matched_refs=matched_refs,
                evidence_refs=evidence_refs,
                exact_version_or_cpe_match=bool(exact_cpes),
                deployment_observed=asset.deployment_observed,
            )
        )
        exposure_status = (
            ExposureStatus.CONFIRMED_EXPOSED if confirmed else ExposureStatus.POTENTIALLY_EXPOSED
        )
        exposure = build_company_exposure(
            identity=inventory.identity,
            threat=ingestion.primary_threat,
            exposure_id=f"exposure:{asset.asset_ref}:{ingestion.cve_id}",
            asset_ref=asset.asset_ref,
            company_evidence_refs=evidence_refs,
            status=exposure_status,
            criticality=asset.criticality,
            patch_status=PatchStatus.UNKNOWN,
            internet_reachable=asset.internet_reachable,
            privileged_identity_surface=asset.privileged,
            compensating_control_present=False,
            assessed_at=as_of,
            recorded_at=as_of,
        )
        exposures.append(exposure)
        priorities.append(
            build_defensive_priority_receipt(
                identity=inventory.identity,
                threat=ingestion.primary_threat,
                exposure=exposure,
                as_of=as_of,
                max_company_evidence_age_seconds=max_company_evidence_age_seconds,
            )
        )

    if any(match.status is CveAssetMatchStatus.CONFIRMED for match in matches):
        status = EayCveImpactStatus.CONFIRMED
        reasons = ["exact_deployed_cpe_match_observed"]
    elif matches:
        status = EayCveImpactStatus.POTENTIAL
        reasons = ["product_or_cpe_match_requires_deployment_or_version_confirmation"]
    elif threat_refs or product_refs:
        status = EayCveImpactStatus.NO_MATCH_OBSERVED
        reasons = ["no_eay_asset_match_observed"]
        if not inventory.inventory_coverage_complete:
            reasons.append("inventory_coverage_incomplete")
    else:
        status = EayCveImpactStatus.UNKNOWN
        reasons = ["threat_has_no_machine_matchable_product_evidence"]

    firm = any(
        priority.firm_company_exposure_claim_authorized
        and priority.exposure_claim is CompanyExposureClaim.AFFECTED
        for priority in priorities
    )
    return _seal(
        EayCveImpactReceipt,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "identity": inventory.identity,
            "cve_id": ingestion.cve_id,
            "as_of": as_of,
            "threat_fingerprint": ingestion.primary_threat.fingerprint,
            "inventory_fingerprint": inventory.fingerprint,
            "status": status,
            "matches": tuple(matches),
            "exposures": tuple(exposures),
            "priorities": tuple(priorities),
            "firm_company_impact_authorized": firm,
            "no_match_is_not_proof_of_safety": True,
            "reason_codes": tuple(reasons),
            "execution_authority_granted": False,
        },
    )


def build_sigma_rule_metadata(
    *,
    rule: Mapping[str, Any],
    evidence_ref: str,
) -> SigmaRuleMetadata:
    logsource = rule.get("logsource") or {}
    if not isinstance(logsource, Mapping):
        raise ValueError("sigma_logsource_mapping_required")
    tags_raw = rule.get("tags") or ()
    if not isinstance(tags_raw, (list, tuple)):
        raise ValueError("sigma_tags_sequence_required")
    tags = tuple(str(tag).lower() for tag in tags_raw)
    attack_ids = tuple(
        sorted(
            {
                tag.split(".", 1)[1].upper()
                for tag in tags
                if tag.startswith("attack.") and _ATTACK.fullmatch(tag.split(".", 1)[1])
            }
        )
    )
    cve_ids: set[str] = set()
    for tag in tags:
        if not tag.startswith("cve."):
            continue
        raw = tag.split(".", 1)[1].upper()
        if raw.startswith("CVE-") and _CVE.fullmatch(raw):
            cve_ids.add(raw)
        else:
            candidate = "CVE-" + raw.replace(".", "-")
            if _CVE.fullmatch(candidate):
                cve_ids.add(candidate)
    draft = {
        "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
        "rule_id": str(rule.get("id") or rule.get("title") or "sigma-rule-unknown"),
        "title": str(rule.get("title") or "Untitled Sigma rule"),
        "status": str(rule.get("status") or "unknown"),
        "level": str(rule["level"]) if rule.get("level") is not None else None,
        "logsource_category": _optional_str(logsource.get("category")),
        "logsource_product": _optional_str(logsource.get("product")),
        "logsource_service": _optional_str(logsource.get("service")),
        "tags": tags,
        "attack_technique_ids": attack_ids,
        "cve_ids": tuple(sorted(cve_ids)),
        "evidence_ref": evidence_ref,
        "detection_body_ingested": False,
        "automatic_deployment_permitted": False,
        "execution_authority_granted": False,
    }
    return _seal(SigmaRuleMetadata, draft)


def build_sigma_telemetry_observation(
    *,
    identity: CompanyIdentity,
    logsource_key: str,
    status: SigmaTelemetryStatus,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    telemetry_ref: str | None = None,
) -> SigmaTelemetryObservation:
    return _seal(
        SigmaTelemetryObservation,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "identity": identity,
            "logsource_key": logsource_key,
            "status": status,
            "evidence_refs": evidence_refs,
            "observed_at": observed_at,
            "recorded_at": recorded_at,
            "telemetry_ref": telemetry_ref,
            "execution_authority_granted": False,
        },
    )


def assess_sigma_coverage(
    *,
    identity: CompanyIdentity,
    ingestion: LiveThreatIngestionReceipt,
    rules: tuple[SigmaRuleMetadata, ...],
    telemetry: tuple[SigmaTelemetryObservation, ...],
    as_of: datetime,
    max_company_evidence_age_seconds: int = 86400,
    attack_technique_ids: tuple[str, ...] = (),
) -> SigmaCoverageReceipt:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    required_attack = {value.upper() for value in attack_technique_ids}
    relevant = tuple(
        rule
        for rule in rules
        if ingestion.cve_id in rule.cve_ids
        or bool(set(rule.attack_technique_ids) & required_attack)
    )
    by_key: dict[str, SigmaTelemetryObservation] = {}
    for raw in telemetry:
        item = SigmaTelemetryObservation.model_validate(raw.model_dump(mode="json"))
        if item.identity.fingerprint != identity.fingerprint:
            raise ValueError("sigma_cross_company_telemetry_forbidden")
        if item.logsource_key in by_key:
            raise ValueError("sigma_duplicate_logsource_observation")
        if item.observed_at > as_of or item.recorded_at > as_of:
            raise ValueError("sigma_future_telemetry_forbidden")
        by_key[item.logsource_key] = item

    covered: list[str] = []
    degraded: list[str] = []
    missing: list[str] = []
    unverified: list[str] = []
    for rule in relevant:
        observed = by_key.get(rule.logsource_key)
        if observed is None or (
            as_of - observed.observed_at
        ).total_seconds() > max_company_evidence_age_seconds:
            unverified.append(rule.rule_id)
        elif observed.status is SigmaTelemetryStatus.AVAILABLE:
            covered.append(rule.rule_id)
        elif observed.status is SigmaTelemetryStatus.DEGRADED:
            degraded.append(rule.rule_id)
        else:
            missing.append(rule.rule_id)

    if not relevant:
        status = SigmaCoverageStatus.NO_RELEVANT_RULE
        firm_gap = False
    elif unverified:
        status = SigmaCoverageStatus.UNVERIFIED
        firm_gap = False
    elif len(covered) == len(relevant):
        status = SigmaCoverageStatus.COVERED
        firm_gap = False
    else:
        status = SigmaCoverageStatus.PARTIAL
        firm_gap = bool(missing or degraded)

    return _seal(
        SigmaCoverageReceipt,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "identity": identity,
            "cve_id": ingestion.cve_id,
            "as_of": as_of,
            "relevant_rule_ids": tuple(rule.rule_id for rule in relevant),
            "covered_rule_ids": tuple(sorted(covered)),
            "degraded_rule_ids": tuple(sorted(degraded)),
            "missing_rule_ids": tuple(sorted(missing)),
            "unverified_rule_ids": tuple(sorted(unverified)),
            "status": status,
            "firm_detection_gap_authorized": firm_gap,
            "automatic_rule_deployment_permitted": False,
            "execution_authority_granted": False,
        },
    )


def triage_company_incident(
    *,
    identity: CompanyIdentity,
    ingestion: LiveThreatIngestionReceipt,
    impact: EayCveImpactReceipt,
    as_of: datetime,
    additional_signals: tuple[CompanySecuritySignal, ...] = (),
) -> CompanyIncidentAssessment | None:
    signals = list(additional_signals)
    if impact.exposures:
        exposure_signal = build_company_security_signal(
            identity=identity,
            signal_id=f"signal:vulnerability:{ingestion.cve_id}:{impact.fingerprint[:12]}",
            signal_type=SecuritySignalType.VULNERABILITY_EXPOSURE,
            evidence_strength=SecurityEvidenceStrength.OBSERVATION,
            source_family=SecuritySourceFamily.VULNERABILITY,
            evidence_refs=(f"impact:{impact.fingerprint[:24]}",),
            observed_at=as_of,
            recorded_at=as_of,
            asset_refs=tuple(exposure.asset_ref for exposure in impact.exposures),
            exposure_refs=tuple(exposure.exposure_id for exposure in impact.exposures),
            threat_record_refs=(ingestion.primary_threat.record_id,),
        )
        signals.append(exposure_signal)
    if not signals:
        return None
    return assess_company_incident(
        identity=identity,
        incident_id=f"incident-review:{ingestion.cve_id}:{_fingerprint({'impact': impact.fingerprint})[:12]}",
        signals=tuple(signals),
        as_of=as_of,
    )


def build_defensive_recommendations(
    *,
    identity: CompanyIdentity,
    ingestion: LiveThreatIngestionReceipt,
    impact: EayCveImpactReceipt,
    sigma: SigmaCoverageReceipt,
) -> tuple[DefensiveResponseCandidate, ...]:
    if not impact.exposures:
        return ()
    by_exposure = {exposure.exposure_id: exposure for exposure in impact.exposures}
    priority_by_exposure = {priority.exposure_id: priority for priority in impact.priorities}
    candidates: list[DefensiveResponseCandidate] = []
    seen_actions: set[tuple[str, DefensiveAction]] = set()

    for exposure_id, exposure in by_exposure.items():
        priority = priority_by_exposure[exposure_id]
        actions = list(priority.recommended_defensive_actions)
        if sigma.status in {SigmaCoverageStatus.UNVERIFIED, SigmaCoverageStatus.PARTIAL}:
            actions.append(DefensiveAction.INCREASE_TELEMETRY)
        if sigma.firm_detection_gap_authorized:
            actions.append(DefensiveAction.DEPLOY_DETECTION_RULE)
        for action in actions:
            key = (exposure_id, action)
            if key in seen_actions:
                continue
            seen_actions.add(key)
            candidates.append(
                build_defensive_response_candidate(
                    identity=identity,
                    threat=ingestion.primary_threat,
                    exposure=exposure,
                    candidate_id=(
                        f"defense:{ingestion.cve_id}:{exposure.asset_ref}:{action.value}"
                    ),
                    action=action,
                    target_ref=exposure.asset_ref,
                    evidence_refs=(
                        f"priority:{priority.fingerprint[:24]}",
                        f"sigma:{sigma.fingerprint[:24]}",
                    ),
                    requires_human_approval=True,
                )
            )
            if len(candidates) >= 8:
                return tuple(candidates)
    return tuple(candidates)


def validate_controlled_sandbox(
    *,
    identity: CompanyIdentity,
    ingestion: LiveThreatIngestionReceipt,
    impact: EayCveImpactReceipt,
    graph: EayAttackGraphReceipt,
    sigma: SigmaCoverageReceipt,
    incident: CompanyIncidentAssessment | None,
    recommendations: tuple[DefensiveResponseCandidate, ...],
    environment_fingerprint: str,
    environment: SandboxEvidenceClass = SandboxEvidenceClass.REPOSITORY_ISOLATED,
    authorization_evidence_ref: str | None = None,
) -> ControlledSandboxValidationReceipt:
    if not _SHA256.fullmatch(environment_fingerprint):
        raise ValueError("cyber_sandbox_environment_fingerprint_invalid")
    checks = (
        SandboxCheck(
            check_id="public-threat-never-company-truth",
            passed=not ingestion.company_truth_granted,
            evidence_ref=f"threat:{ingestion.fingerprint[:24]}",
        ),
        SandboxCheck(
            check_id="firm-impact-requires-canonical-company-proof",
            passed=(
                not impact.firm_company_impact_authorized
                or any(
                    p.firm_company_exposure_claim_authorized
                    and p.exposure_claim is CompanyExposureClaim.AFFECTED
                    for p in impact.priorities
                )
            ),
            evidence_ref=f"impact:{impact.fingerprint[:24]}",
        ),
        SandboxCheck(
            check_id="graph-never-proves-attack",
            passed=(
                not graph.attack_success_proven
                and not graph.incident_confirmation_granted
                and not graph.execution_authority_granted
            ),
            evidence_ref=f"graph:{graph.fingerprint[:24]}",
        ),
        SandboxCheck(
            check_id="sigma-never-auto-deploys",
            passed=(
                not sigma.automatic_rule_deployment_permitted
                and not sigma.execution_authority_granted
            ),
            evidence_ref=f"sigma:{sigma.fingerprint[:24]}",
        ),
        SandboxCheck(
            check_id="incident-no-attribution-or-causality-overclaim",
            passed=(
                incident is None
                or (
                    not incident.threat_actor_attribution_proven
                    and not incident.causal_claim_proven
                    and not incident.execution_authority_granted
                )
            ),
            evidence_ref=(
                f"incident:{incident.fingerprint[:24]}" if incident else "incident:none"
            ),
        ),
        SandboxCheck(
            check_id="recommendations-candidate-only",
            passed=all(
                not candidate.execution_authority_granted
                and candidate.requires_effect_verification
                for candidate in recommendations
            ),
            evidence_ref=f"recommendations:{len(recommendations)}",
        ),
    )
    return _seal(
        ControlledSandboxValidationReceipt,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "identity": identity,
            "environment": environment,
            "environment_fingerprint": environment_fingerprint,
            "authorization_evidence_ref": authorization_evidence_ref,
            "checks": checks,
            "passed": all(check.passed for check in checks),
            "qualifies_as_authorized_sandbox_benchmark_evidence": (
                environment is SandboxEvidenceClass.AUTHORIZED_EXTERNAL
                and bool(authorization_evidence_ref)
                and all(check.passed for check in checks)
            ),
            "destructive_actions_allowed": False,
            "exploit_generation_allowed": False,
            "credential_capture_allowed": False,
            "production_write_allowed": False,
            "execution_authority_granted": False,
        },
    )


def build_continuous_benchmark_checkpoint(
    *,
    profile: CyberBenchmarkProfile,
    system_id: str,
    system_version: str,
    revision_ref: str,
    environment_fingerprint: str,
    measured_at: datetime,
    measurements: tuple[MetricMeasurement, ...],
    baseline: BenchmarkRun | None = None,
) -> ContinuousCyberBenchmarkCheckpoint:
    profile = CyberBenchmarkProfile.model_validate(profile.model_dump(mode="json"))
    run = build_cyber_benchmark_run(
        profile=profile,
        system_id=system_id,
        system_version=system_version,
        environment_fingerprint=environment_fingerprint,
        measured_at=measured_at,
        measurements=measurements,
    )
    comparison = (
        compare_cyber_benchmark_runs(profile=profile, challenger=run, baseline=baseline)
        if baseline is not None
        else None
    )
    return _seal(
        ContinuousCyberBenchmarkCheckpoint,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "revision_ref": revision_ref,
            "profile_fingerprint": profile.fingerprint,
            "evidence_class": profile.evidence_class,
            "run": run,
            "comparison": comparison,
            "benchmark_superiority_claim_allowed": bool(
                comparison and comparison.benchmark_superiority_claim_allowed
            ),
            "production_security_superiority_claim_allowed": False,
            "automatic_promotion_allowed": False,
            "execution_authority_granted": False,
        },
    )


def run_continuous_defense_cycle(
    *,
    identity: CompanyIdentity,
    ingestion: LiveThreatIngestionReceipt,
    inventory: EayAssetInventorySnapshot,
    sigma_rules: tuple[SigmaRuleMetadata, ...],
    sigma_telemetry: tuple[SigmaTelemetryObservation, ...],
    as_of: datetime,
    sandbox_environment_fingerprint: str,
    additional_incident_signals: tuple[CompanySecuritySignal, ...] = (),
    attack_technique_ids: tuple[str, ...] = (),
    benchmark: ContinuousCyberBenchmarkCheckpoint | None = None,
) -> ContinuousDefenseCycleReceipt:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    if inventory.identity.fingerprint != identity.fingerprint:
        raise ValueError("continuous_cyber_cycle_cross_company_inventory_forbidden")
    impact = assess_eay_cve_impact(
        ingestion=ingestion,
        inventory=inventory,
        as_of=as_of,
    )
    graph = materialize_eay_attack_graph(
        inventory=inventory,
        affected_entry_refs=tuple(match.asset_ref for match in impact.matches),
    )
    sigma = assess_sigma_coverage(
        identity=identity,
        ingestion=ingestion,
        rules=sigma_rules,
        telemetry=sigma_telemetry,
        as_of=as_of,
        attack_technique_ids=attack_technique_ids,
    )
    incident = triage_company_incident(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        as_of=as_of,
        additional_signals=additional_incident_signals,
    )
    recommendations = build_defensive_recommendations(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        sigma=sigma,
    )
    sandbox = validate_controlled_sandbox(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        graph=graph,
        sigma=sigma,
        incident=incident,
        recommendations=recommendations,
        environment_fingerprint=sandbox_environment_fingerprint,
    )
    return _seal(
        ContinuousDefenseCycleReceipt,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "identity": identity,
            "threat": ingestion,
            "impact": impact,
            "graph": graph,
            "sigma": sigma,
            "incident": incident,
            "recommendations": recommendations,
            "sandbox": sandbox,
            "benchmark": benchmark,
            "automatic_remediation_permitted": False,
            "production_write_permitted": False,
            "exploit_generation_permitted": False,
            "execution_authority_granted": False,
        },
    )


def latest_kev_cve_id(payload: Mapping[str, Any]) -> str:
    entries = payload.get("vulnerabilities")
    if not isinstance(entries, list) or not entries:
        raise LiveThreatSourceUnavailable("cyber_live_kev_catalog_empty")
    dated: list[tuple[date, str]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        cve_id = str(entry.get("cveID") or "").upper()
        date_added = entry.get("dateAdded")
        if _CVE.fullmatch(cve_id) and isinstance(date_added, str):
            try:
                dated.append((date.fromisoformat(date_added), cve_id))
            except ValueError:
                continue
    if not dated:
        raise LiveThreatSourceUnavailable("cyber_live_kev_catalog_has_no_valid_entries")
    dated.sort(reverse=True)
    return dated[0][1]


def _feed_observation(
    *,
    source: LiveThreatFeedSource,
    transport: FeedTransport,
    status: FeedObservationStatus,
    endpoint_ref: str,
    observed_at: datetime,
    http_status: int,
    content_sha256: str,
    canonical_authority_observed: bool,
) -> PublicFeedObservation:
    return _seal(
        PublicFeedObservation,
        {
            "contract": CYBER_CONTINUOUS_DEFENSE_CONTRACT,
            "source": source,
            "transport": transport,
            "status": status,
            "endpoint_ref": endpoint_ref,
            "observed_at": observed_at,
            "http_status": http_status,
            "content_sha256": content_sha256,
            "canonical_authority_observed": canonical_authority_observed,
            "evidence_ref": f"public-feed:{source.value}:{content_sha256[:24]}",
            "credentials_sent": False,
            "arbitrary_url_allowed": False,
            "execution_authority_granted": False,
        },
    )


def _validate_public_endpoint(url: str) -> None:
    if url not in _ALLOWED_ENDPOINTS:
        raise ValueError("cyber_live_feed_endpoint_not_allowlisted")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("cyber_live_feed_https_required")


def _extract_nvd_cve(payload: Mapping[str, Any], cve_id: str) -> Mapping[str, Any]:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise LiveThreatSourceUnavailable("nvd_vulnerabilities_list_missing")
    for wrapper in vulnerabilities:
        if not isinstance(wrapper, Mapping):
            continue
        cve = wrapper.get("cve")
        if isinstance(cve, Mapping) and str(cve.get("id") or "").upper() == cve_id.upper():
            return cve
    raise LiveThreatSourceUnavailable("nvd_exact_cve_not_found")


def _extract_nvd_cwes(cve: Mapping[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    weaknesses = cve.get("weaknesses") or []
    if isinstance(weaknesses, list):
        for weakness in weaknesses:
            if not isinstance(weakness, Mapping):
                continue
            for description in weakness.get("description") or []:
                if isinstance(description, Mapping):
                    value = str(description.get("value") or "").upper()
                    if _CWE.fullmatch(value):
                        values.add(value)
    return tuple(sorted(values))


def _extract_nvd_cpes(cve: Mapping[str, Any]) -> tuple[str, ...]:
    refs: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            criteria = value.get("criteria")
            if isinstance(criteria, str) and criteria.startswith("cpe:2.3:"):
                refs.add(criteria)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(cve.get("configurations") or [])
    return tuple(sorted(refs))


def _extract_nvd_severity(cve: Mapping[str, Any]) -> float | None:
    metrics = cve.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        values = metrics.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping):
                continue
            data = value.get("cvssData")
            if isinstance(data, Mapping) and data.get("baseScore") is not None:
                try:
                    score = float(data["baseScore"])
                except (TypeError, ValueError):
                    continue
                if 0.0 <= score <= 10.0:
                    return score
    return None


def _find_kev_entry(payload: Mapping[str, Any], cve_id: str) -> Mapping[str, Any] | None:
    entries = payload.get("vulnerabilities")
    if not isinstance(entries, list):
        raise LiveThreatSourceUnavailable("cisa_kev_vulnerabilities_list_missing")
    for entry in entries:
        if isinstance(entry, Mapping) and str(entry.get("cveID") or "").upper() == cve_id.upper():
            return entry
    return None


def _extract_epss_item(payload: Mapping[str, Any], cve_id: str) -> Mapping[str, Any] | None:
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    for item in data:
        if isinstance(item, Mapping) and str(item.get("cve") or "").upper() == cve_id.upper():
            return item
    return None


def _vendor_product_ref(vendor: Any, product: Any) -> str:
    vendor_value = _normalize_product_part(vendor)
    product_value = _normalize_product_part(product)
    return f"vendor-product:{vendor_value}:{product_value}"


def _normalize_product_part(value: Any) -> str:
    raw = str(value or "unknown").strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-")
    return normalized or "unknown"


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise LiveThreatSourceUnavailable("cyber_live_source_datetime_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LiveThreatSourceUnavailable("cyber_live_source_datetime_invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_date_as_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise LiveThreatSourceUnavailable("cyber_live_source_date_missing")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise LiveThreatSourceUnavailable("cyber_live_source_date_invalid") from exc
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cve(value: str) -> None:
    if not _CVE.fullmatch(value):
        raise ValueError("cyber_invalid_cve_id")


def _same_identity(expected: CompanyIdentity, actual: CompanyIdentity) -> None:
    if expected.fingerprint != actual.fingerprint:
        raise ValueError("cyber_cross_company_identity_forbidden")


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _seal(model_cls: type[BaseModel], values: Mapping[str, Any]):
    draft = model_cls.model_construct(**dict(values), fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_cls.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
