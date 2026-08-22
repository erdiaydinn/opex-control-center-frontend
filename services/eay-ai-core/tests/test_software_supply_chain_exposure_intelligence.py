from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.company_context_boundary import build_company_identity
from app.company_cyber_incident_intelligence import (
    IncidentStatus,
    SecurityEvidenceStrength,
    SecuritySourceFamily,
    assess_company_incident,
)
from app.cyber_defense_intelligence import (
    ThreatIntelligenceSource,
    build_threat_record,
)
from app.software_supply_chain_exposure import (
    ComponentDeploymentAttestation,
    ComponentEvidenceScope,
    ComponentIdentityKind,
    ComponentThreatMatchStrength,
    DeploymentEvidenceKind,
    SupplyChainExposureStatus,
    assess_supply_chain_exposure,
    build_component_observation,
    build_component_threat_match,
    build_deployment_attestation,
    exposure_to_security_signal,
)

T1 = datetime(2026, 8, 18, 8, tzinfo=UTC)
T2 = datetime(2026, 8, 19, 8, tzinfo=UTC)


def _company(*, tenant: str = "tenant-a", company: str = "company-a"):
    return build_company_identity(
        tenant_id=tenant,
        company_id=company,
        company_slug=company,
        profile_revision="rev-1",
        environment="production",
    )


def _threat():
    return build_threat_record(
        record_id="cisa-kev:cve-2026-45678",
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-45678",
        published_at=T1,
        recorded_at=T2,
        source_evidence_ref="cisa:kev:cve-2026-45678",
        cve_ids=("CVE-2026-45678",),
        severity_score=9.8,
        known_exploited_in_wild=True,
    )


def _component(identity, *, scope: ComponentEvidenceScope):
    kwargs = {}
    if scope is ComponentEvidenceScope.REPOSITORY:
        kwargs["repository_ref"] = "repo:eay:core"
    elif scope is ComponentEvidenceScope.BUILD_ARTIFACT:
        kwargs["build_ref"] = "build:sha256:abc123"
    else:
        kwargs["asset_ref"] = "asset:api-prod-1"
    return build_component_observation(
        identity=identity,
        observation_id=f"component:{scope.value}",
        scope=scope,
        identity_kind=ComponentIdentityKind.PURL,
        component_ref="pkg:pypi/example-library@1.2.3",
        version_ref="1.2.3",
        evidence_refs=(f"evidence:sbom:{scope.value}",),
        observed_at=T2,
        recorded_at=T2,
        **kwargs,
    )


def _exact_match(identity, component, *, inferred: bool = False):
    return build_component_threat_match(
        identity=identity,
        threat=_threat(),
        component=component,
        match_id=f"match:{component.scope.value}",
        strength=ComponentThreatMatchStrength.EXACT,
        match_evidence_refs=("evidence:scanner:exact-component-version",),
        inferred_version_range=inferred,
    )


def test_exact_repository_dependency_never_becomes_runtime_exposure() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.REPOSITORY)
    match = _exact_match(identity, component)
    exposure = assess_supply_chain_exposure(
        identity=identity,
        threat=_threat(),
        component=component,
        match=match,
        assessment_id="assessment:repo",
    )
    assert exposure.status is SupplyChainExposureStatus.REPOSITORY_ONLY
    assert exposure.runtime_exposure_confirmed is False
    assert exposure.asset_ref is None
    assert exposure.incident_confirmation_granted is False
    assert exposure.execution_authority_granted is False


def test_exact_build_artifact_match_is_not_deployment_truth() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.BUILD_ARTIFACT)
    exposure = assess_supply_chain_exposure(
        identity=identity,
        threat=_threat(),
        component=component,
        match=_exact_match(identity, component),
        assessment_id="assessment:build",
    )
    assert exposure.status is SupplyChainExposureStatus.BUILD_ONLY
    assert exposure.runtime_exposure_confirmed is False
    assert exposure.deployment_attestation_id is None


def test_deployed_component_without_attestation_stays_potential() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.DEPLOYED_ASSET)
    exposure = assess_supply_chain_exposure(
        identity=identity,
        threat=_threat(),
        component=component,
        match=_exact_match(identity, component),
        assessment_id="assessment:deployed-unattested",
    )
    assert exposure.status is SupplyChainExposureStatus.POTENTIALLY_EXPOSED
    assert exposure.runtime_exposure_confirmed is False


def test_exact_match_plus_runtime_deployment_attestation_confirms_exposure_only() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.DEPLOYED_ASSET)
    deployment = build_deployment_attestation(
        identity=identity,
        component=component,
        attestation_id="deployment:api-prod-1",
        asset_ref="asset:api-prod-1",
        evidence_kind=DeploymentEvidenceKind.RUNTIME_INVENTORY,
        evidence_refs=("evidence:runtime-inventory:api-prod-1",),
        observed_at=T2,
        recorded_at=T2,
    )
    exposure = assess_supply_chain_exposure(
        identity=identity,
        threat=_threat(),
        component=component,
        match=_exact_match(identity, component),
        assessment_id="assessment:confirmed",
        deployment=deployment,
    )
    assert exposure.status is SupplyChainExposureStatus.CONFIRMED_EXPOSED
    assert exposure.runtime_exposure_confirmed is True
    assert exposure.asset_ref == "asset:api-prod-1"
    assert exposure.incident_confirmation_granted is False
    assert exposure.execution_authority_granted is False


def test_possible_match_never_confirms_runtime_exposure_even_with_deployment() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.DEPLOYED_ASSET)
    deployment = build_deployment_attestation(
        identity=identity,
        component=component,
        attestation_id="deployment:possible",
        asset_ref="asset:api-prod-1",
        evidence_kind=DeploymentEvidenceKind.RUNTIME_TELEMETRY,
        evidence_refs=("evidence:runtime:api-prod-1",),
        observed_at=T2,
        recorded_at=T2,
    )
    match = build_component_threat_match(
        identity=identity,
        threat=_threat(),
        component=component,
        match_id="match:possible",
        strength=ComponentThreatMatchStrength.POSSIBLE,
        match_evidence_refs=("evidence:scanner:possible-range",),
        inferred_version_range=True,
    )
    exposure = assess_supply_chain_exposure(
        identity=identity,
        threat=_threat(),
        component=component,
        match=match,
        assessment_id="assessment:possible",
        deployment=deployment,
    )
    assert exposure.status is SupplyChainExposureStatus.POTENTIALLY_EXPOSED
    assert exposure.runtime_exposure_confirmed is False


def test_exact_match_cannot_be_based_on_inferred_version_range() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.REPOSITORY)
    with pytest.raises(ValueError, match="supply_exact_match_cannot_be_inferred_version_range"):
        _exact_match(identity, component, inferred=True)


def test_cross_company_component_or_deployment_cannot_leak() -> None:
    company_a = _company(tenant="tenant-a", company="company-a")
    company_b = _company(tenant="tenant-b", company="company-b")
    component = _component(company_a, scope=ComponentEvidenceScope.DEPLOYED_ASSET)
    with pytest.raises(ValueError, match="supply_match_company_mismatch"):
        build_component_threat_match(
            identity=company_b,
            threat=_threat(),
            component=component,
            match_id="match:cross-company",
            strength=ComponentThreatMatchStrength.EXACT,
            match_evidence_refs=("evidence:scanner:exact",),
        )


def test_confirmed_supply_exposure_becomes_observation_not_incident_confirmation() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.DEPLOYED_ASSET)
    deployment = build_deployment_attestation(
        identity=identity,
        component=component,
        attestation_id="deployment:signal",
        asset_ref="asset:api-prod-1",
        evidence_kind=DeploymentEvidenceKind.SIGNED_DEPLOYMENT_MANIFEST,
        evidence_refs=("evidence:signed-manifest:api-prod-1",),
        observed_at=T2,
        recorded_at=T2,
    )
    exposure = assess_supply_chain_exposure(
        identity=identity,
        threat=_threat(),
        component=component,
        match=_exact_match(identity, component),
        assessment_id="assessment:signal",
        deployment=deployment,
    )
    signal = exposure_to_security_signal(
        identity=identity,
        exposure=exposure,
        signal_id="signal:supply-chain-exposure",
        observed_at=T2,
        recorded_at=T2,
    )
    assert signal.evidence_strength is SecurityEvidenceStrength.OBSERVATION
    assert signal.source_family is SecuritySourceFamily.SUPPLY_CHAIN
    assert signal.compromise_confirmed is False

    incident = assess_company_incident(
        identity=identity,
        incident_id="incident:supply-chain-only",
        signals=(signal,),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.UNCONFIRMED
    assert incident.execution_authority_granted is False


def test_secret_bearing_component_evidence_is_rejected() -> None:
    identity = _company()
    with pytest.raises(ValueError, match="supply_component_unsafe_reference_forbidden"):
        build_component_observation(
            identity=identity,
            observation_id="component:unsafe",
            scope=ComponentEvidenceScope.REPOSITORY,
            identity_kind=ComponentIdentityKind.PURL,
            component_ref="pkg:pypi/example@1.0",
            version_ref="1.0",
            repository_ref="repo:eay:core",
            evidence_refs=("authorization:bearer-material",),
            observed_at=T2,
            recorded_at=T2,
        )


def test_deployment_attestation_fingerprint_tamper_fails_closed() -> None:
    identity = _company()
    component = _component(identity, scope=ComponentEvidenceScope.DEPLOYED_ASSET)
    deployment = build_deployment_attestation(
        identity=identity,
        component=component,
        attestation_id="deployment:tamper",
        asset_ref="asset:api-prod-1",
        evidence_kind=DeploymentEvidenceKind.RUNTIME_INVENTORY,
        evidence_refs=("evidence:runtime-inventory:api-prod-1",),
        observed_at=T2,
        recorded_at=T2,
    )
    tampered = deployment.model_copy(update={"asset_ref": "asset:api-prod-2"})
    with pytest.raises(ValueError, match="supply_deployment_fingerprint_mismatch"):
        ComponentDeploymentAttestation.model_validate(tampered.model_dump(mode="json"))
