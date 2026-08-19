"""Evidence-bound software supply-chain exposure reasoning for EAY Jarvis.

Repository dependency presence is not deployment truth. Build-artifact presence
is not deployment truth. Even an exact vulnerability/component match is only a
match until company deployment evidence binds that component to a deployed
asset. This module performs no package resolution, network I/O or execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.company_cyber_incident_intelligence import (
    CompanySecuritySignal,
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    build_company_security_signal,
)
from app.cyber_defense_intelligence import ThreatKnowledgeRecord

SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT = "eay-software-supply-chain-exposure-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class ComponentEvidenceScope(str, Enum):
    REPOSITORY = "repository"
    BUILD_ARTIFACT = "build_artifact"
    DEPLOYED_ASSET = "deployed_asset"


class ComponentIdentityKind(str, Enum):
    PURL = "purl"
    CPE = "cpe"
    SBOM_COMPONENT = "sbom_component"
    PACKAGE_COORDINATE = "package_coordinate"


class ComponentThreatMatchStrength(str, Enum):
    POSSIBLE = "possible"
    EXACT = "exact"


class DeploymentEvidenceKind(str, Enum):
    SIGNED_DEPLOYMENT_MANIFEST = "signed_deployment_manifest"
    RUNTIME_INVENTORY = "runtime_inventory"
    RUNTIME_TELEMETRY = "runtime_telemetry"


class SupplyChainExposureStatus(str, Enum):
    REPOSITORY_ONLY = "repository_only"
    BUILD_ONLY = "build_only"
    POTENTIALLY_EXPOSED = "potentially_exposed"
    CONFIRMED_EXPOSED = "confirmed_exposed"


class SoftwareComponentObservation(BaseModel):
    contract: str = SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT
    observation_id: str = Field(min_length=1)
    identity: CompanyIdentity
    scope: ComponentEvidenceScope
    identity_kind: ComponentIdentityKind
    component_ref: str = Field(min_length=1)
    version_ref: str = Field(min_length=1)
    repository_ref: str | None = None
    build_ref: str | None = None
    asset_ref: str | None = None
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    deployment_truth_granted: bool = False
    vulnerability_truth_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def component_is_integral_and_non_authoritative(
        self,
    ) -> "SoftwareComponentObservation":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.observed_at, "supply_component_observed_at_requires_timezone")
        _aware(self.recorded_at, "supply_component_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("supply_component_recorded_at_predates_observation")
        if self.scope is ComponentEvidenceScope.REPOSITORY:
            if self.repository_ref is None:
                raise ValueError("supply_repository_component_requires_repository_ref")
            if self.asset_ref is not None:
                raise ValueError("supply_repository_component_cannot_claim_asset")
        elif self.scope is ComponentEvidenceScope.BUILD_ARTIFACT:
            if self.build_ref is None:
                raise ValueError("supply_build_component_requires_build_ref")
            if self.asset_ref is not None:
                raise ValueError("supply_build_component_cannot_claim_asset")
        elif self.asset_ref is None:
            raise ValueError("supply_deployed_component_requires_asset_ref")
        if self.deployment_truth_granted:
            raise ValueError("supply_component_observation_never_grants_deployment_truth")
        if self.vulnerability_truth_granted:
            raise ValueError("supply_component_observation_never_grants_vulnerability_truth")
        if self.execution_authority_granted:
            raise ValueError("supply_component_observation_never_grants_execution_authority")
        _unique(self.evidence_refs, "supply_component_evidence_refs_must_be_unique")
        for ref in (
            self.observation_id,
            self.component_ref,
            self.version_ref,
            self.repository_ref,
            self.build_ref,
            self.asset_ref,
            *self.evidence_refs,
        ):
            if ref is not None:
                _safe_ref(ref, "supply_component_unsafe_reference_forbidden")
        _verify(self, "supply_component_fingerprint_mismatch")
        return self


class ComponentDeploymentAttestation(BaseModel):
    contract: str = SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT
    attestation_id: str = Field(min_length=1)
    identity: CompanyIdentity
    component_observation_id: str = Field(min_length=1)
    component_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_ref: str = Field(min_length=1)
    evidence_kind: DeploymentEvidenceKind
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    repository_evidence_only: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def deployment_is_strong_company_evidence(self) -> "ComponentDeploymentAttestation":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.observed_at, "supply_deployment_observed_at_requires_timezone")
        _aware(self.recorded_at, "supply_deployment_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("supply_deployment_recorded_at_predates_observation")
        if self.repository_evidence_only:
            raise ValueError("supply_deployment_cannot_be_repository_evidence_only")
        if self.execution_authority_granted:
            raise ValueError("supply_deployment_never_grants_execution_authority")
        _unique(self.evidence_refs, "supply_deployment_evidence_refs_must_be_unique")
        for ref in (
            self.attestation_id,
            self.component_observation_id,
            self.asset_ref,
            *self.evidence_refs,
        ):
            _safe_ref(ref, "supply_deployment_unsafe_reference_forbidden")
        _verify(self, "supply_deployment_fingerprint_mismatch")
        return self


class ComponentThreatMatch(BaseModel):
    contract: str = SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT
    match_id: str = Field(min_length=1)
    identity: CompanyIdentity
    threat_record_id: str = Field(min_length=1)
    threat_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    component_observation_id: str = Field(min_length=1)
    component_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    strength: ComponentThreatMatchStrength
    match_evidence_refs: tuple[str, ...] = Field(min_length=1)
    inferred_version_range: bool = False
    deployment_truth_granted: bool = False
    company_exposure_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def match_is_non_authoritative(self) -> "ComponentThreatMatch":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if self.strength is ComponentThreatMatchStrength.EXACT and self.inferred_version_range:
            raise ValueError("supply_exact_match_cannot_be_inferred_version_range")
        if self.deployment_truth_granted:
            raise ValueError("supply_match_never_grants_deployment_truth")
        if self.company_exposure_granted:
            raise ValueError("supply_match_never_grants_company_exposure")
        if self.execution_authority_granted:
            raise ValueError("supply_match_never_grants_execution_authority")
        _unique(self.match_evidence_refs, "supply_match_evidence_refs_must_be_unique")
        for ref in (
            self.match_id,
            self.threat_record_id,
            self.component_observation_id,
            *self.match_evidence_refs,
        ):
            _safe_ref(ref, "supply_match_unsafe_reference_forbidden")
        _verify(self, "supply_match_fingerprint_mismatch")
        return self


class SupplyChainExposureAssessment(BaseModel):
    contract: str = SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT
    assessment_id: str = Field(min_length=1)
    identity: CompanyIdentity
    threat_record_id: str = Field(min_length=1)
    component_observation_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    deployment_attestation_id: str | None = None
    status: SupplyChainExposureStatus
    asset_ref: str | None = None
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    runtime_exposure_confirmed: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def assessment_preserves_truth_boundary(self) -> "SupplyChainExposureAssessment":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if self.status is SupplyChainExposureStatus.CONFIRMED_EXPOSED:
            if not self.runtime_exposure_confirmed:
                raise ValueError("supply_confirmed_exposure_requires_runtime_confirmation")
            if self.asset_ref is None or self.deployment_attestation_id is None:
                raise ValueError("supply_confirmed_exposure_requires_deployment_binding")
        elif self.runtime_exposure_confirmed:
            raise ValueError("supply_runtime_confirmation_requires_confirmed_status")
        if self.incident_confirmation_granted:
            raise ValueError("supply_exposure_never_confirms_incident")
        if self.execution_authority_granted:
            raise ValueError("supply_exposure_never_grants_execution_authority")
        _unique(self.evidence_refs, "supply_exposure_evidence_refs_must_be_unique")
        _verify(self, "supply_exposure_fingerprint_mismatch")
        return self


def build_component_observation(
    *,
    identity: CompanyIdentity,
    observation_id: str,
    scope: ComponentEvidenceScope,
    identity_kind: ComponentIdentityKind,
    component_ref: str,
    version_ref: str,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    repository_ref: str | None = None,
    build_ref: str | None = None,
    asset_ref: str | None = None,
) -> SoftwareComponentObservation:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT,
        "observation_id": observation_id,
        "identity": identity.model_dump(mode="json"),
        "scope": scope.value,
        "identity_kind": identity_kind.value,
        "component_ref": component_ref,
        "version_ref": version_ref,
        "repository_ref": repository_ref,
        "build_ref": build_ref,
        "asset_ref": asset_ref,
        "evidence_refs": list(evidence_refs),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "deployment_truth_granted": False,
        "vulnerability_truth_granted": False,
        "execution_authority_granted": False,
    }
    return SoftwareComponentObservation.model_validate(_sealed(draft))


def build_deployment_attestation(
    *,
    identity: CompanyIdentity,
    component: SoftwareComponentObservation,
    attestation_id: str,
    asset_ref: str,
    evidence_kind: DeploymentEvidenceKind,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
) -> ComponentDeploymentAttestation:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    component = SoftwareComponentObservation.model_validate(
        component.model_dump(mode="json")
    )
    _same_company(identity, component.identity, "supply_deployment_company_mismatch")
    if component.scope is not ComponentEvidenceScope.DEPLOYED_ASSET:
        raise ValueError("supply_deployment_attestation_requires_deployed_component")
    if component.asset_ref != asset_ref:
        raise ValueError("supply_deployment_asset_mismatch")
    draft = {
        "contract": SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT,
        "attestation_id": attestation_id,
        "identity": identity.model_dump(mode="json"),
        "component_observation_id": component.observation_id,
        "component_fingerprint": component.fingerprint,
        "asset_ref": asset_ref,
        "evidence_kind": evidence_kind.value,
        "evidence_refs": list(evidence_refs),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "repository_evidence_only": False,
        "execution_authority_granted": False,
    }
    return ComponentDeploymentAttestation.model_validate(_sealed(draft))


def build_component_threat_match(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    component: SoftwareComponentObservation,
    match_id: str,
    strength: ComponentThreatMatchStrength,
    match_evidence_refs: tuple[str, ...],
    inferred_version_range: bool = False,
) -> ComponentThreatMatch:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    threat = ThreatKnowledgeRecord.model_validate(threat.model_dump(mode="json"))
    component = SoftwareComponentObservation.model_validate(
        component.model_dump(mode="json")
    )
    _same_company(identity, component.identity, "supply_match_company_mismatch")
    draft = {
        "contract": SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT,
        "match_id": match_id,
        "identity": identity.model_dump(mode="json"),
        "threat_record_id": threat.record_id,
        "threat_fingerprint": threat.fingerprint,
        "component_observation_id": component.observation_id,
        "component_fingerprint": component.fingerprint,
        "strength": strength.value,
        "match_evidence_refs": list(match_evidence_refs),
        "inferred_version_range": inferred_version_range,
        "deployment_truth_granted": False,
        "company_exposure_granted": False,
        "execution_authority_granted": False,
    }
    return ComponentThreatMatch.model_validate(_sealed(draft))


def assess_supply_chain_exposure(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    component: SoftwareComponentObservation,
    match: ComponentThreatMatch,
    assessment_id: str,
    deployment: ComponentDeploymentAttestation | None = None,
) -> SupplyChainExposureAssessment:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    threat = ThreatKnowledgeRecord.model_validate(threat.model_dump(mode="json"))
    component = SoftwareComponentObservation.model_validate(
        component.model_dump(mode="json")
    )
    match = ComponentThreatMatch.model_validate(match.model_dump(mode="json"))
    _same_company(identity, component.identity, "supply_exposure_company_mismatch")
    _same_company(identity, match.identity, "supply_exposure_match_company_mismatch")
    if match.threat_record_id != threat.record_id or match.threat_fingerprint != threat.fingerprint:
        raise ValueError("supply_exposure_threat_binding_mismatch")
    if (
        match.component_observation_id != component.observation_id
        or match.component_fingerprint != component.fingerprint
    ):
        raise ValueError("supply_exposure_component_binding_mismatch")

    deployment_id: str | None = None
    asset_ref: str | None = None
    evidence = set(component.evidence_refs) | set(match.match_evidence_refs)
    if match.strength is ComponentThreatMatchStrength.POSSIBLE:
        status = SupplyChainExposureStatus.POTENTIALLY_EXPOSED
        runtime_confirmed = False
    elif component.scope is ComponentEvidenceScope.REPOSITORY:
        status = SupplyChainExposureStatus.REPOSITORY_ONLY
        runtime_confirmed = False
    elif component.scope is ComponentEvidenceScope.BUILD_ARTIFACT:
        status = SupplyChainExposureStatus.BUILD_ONLY
        runtime_confirmed = False
    else:
        if deployment is None:
            status = SupplyChainExposureStatus.POTENTIALLY_EXPOSED
            runtime_confirmed = False
        else:
            deployment = ComponentDeploymentAttestation.model_validate(
                deployment.model_dump(mode="json")
            )
            _same_company(
                identity,
                deployment.identity,
                "supply_exposure_deployment_company_mismatch",
            )
            if (
                deployment.component_observation_id != component.observation_id
                or deployment.component_fingerprint != component.fingerprint
                or deployment.asset_ref != component.asset_ref
            ):
                raise ValueError("supply_exposure_deployment_binding_mismatch")
            status = SupplyChainExposureStatus.CONFIRMED_EXPOSED
            runtime_confirmed = True
            deployment_id = deployment.attestation_id
            asset_ref = deployment.asset_ref
            evidence.update(deployment.evidence_refs)

    draft = {
        "contract": SOFTWARE_SUPPLY_CHAIN_EXPOSURE_CONTRACT,
        "assessment_id": assessment_id,
        "identity": identity.model_dump(mode="json"),
        "threat_record_id": threat.record_id,
        "component_observation_id": component.observation_id,
        "match_id": match.match_id,
        "deployment_attestation_id": deployment_id,
        "status": status.value,
        "asset_ref": asset_ref,
        "evidence_refs": sorted(evidence),
        "runtime_exposure_confirmed": runtime_confirmed,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    return SupplyChainExposureAssessment.model_validate(_sealed(draft))


def exposure_to_security_signal(
    *,
    identity: CompanyIdentity,
    exposure: SupplyChainExposureAssessment,
    signal_id: str,
    observed_at: datetime,
    recorded_at: datetime,
) -> CompanySecuritySignal:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    exposure = SupplyChainExposureAssessment.model_validate(
        exposure.model_dump(mode="json")
    )
    _same_company(identity, exposure.identity, "supply_signal_company_mismatch")
    assets = (exposure.asset_ref,) if exposure.asset_ref is not None else ()
    return build_company_security_signal(
        identity=identity,
        signal_id=signal_id,
        signal_type=SecuritySignalType.VULNERABILITY_EXPOSURE,
        evidence_strength=SecurityEvidenceStrength.OBSERVATION,
        source_family=SecuritySourceFamily.SUPPLY_CHAIN,
        evidence_refs=exposure.evidence_refs,
        asset_refs=assets,
        exposure_refs=(f"supply-exposure:{exposure.assessment_id}",),
        threat_record_refs=(exposure.threat_record_id,),
        observed_at=observed_at,
        recorded_at=recorded_at,
    )


def _same_company(identity: CompanyIdentity, other: CompanyIdentity, error: str) -> None:
    if identity.fingerprint != other.fingerprint:
        raise ValueError(error)


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
    _aware(value, "supply_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _verify(model: BaseModel, error: str) -> None:
    if getattr(model, "fingerprint") != _fingerprint(_payload(model)):
        raise ValueError(error)


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
