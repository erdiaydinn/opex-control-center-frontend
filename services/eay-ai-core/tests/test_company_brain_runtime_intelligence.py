from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.company_brain_runtime import (
    CANONICAL_COMPANY_BRAIN_PLANES,
    CompanyBrainOnboardingStage,
    CompanyRuntimeDisposition,
    assess_company_brain_onboarding,
    bind_company_runtime_request,
    validate_company_runtime_request_binding,
)
from app.company_context_boundary import (
    CompanyContextPlane,
    build_company_context_binding,
    build_company_context_snapshot,
    build_company_identity,
)

T0 = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
ARTIFACT_FP = "a" * 64


def _identity(company: str, revision: str = "v1"):
    return build_company_identity(
        tenant_id="tenant://multi-company",
        company_id=f"company://{company}",
        company_slug=company,
        profile_revision=revision,
        environment="production",
    )


def _binding(identity, plane: CompanyContextPlane, index: int):
    return build_company_context_binding(
        identity=identity,
        binding_id=f"binding://{identity.company_slug}/{plane.value}/{index}",
        plane=plane,
        artifact_ref=f"company-artifact://{identity.company_slug}/{plane.value}/v1",
        artifact_fingerprint=ARTIFACT_FP,
        effective_from=T0,
        observed_at=T0,
        recorded_at=T0,
        evidence_refs=(f"evidence://{identity.company_slug}/{plane.value}/{index}",),
    )


def _snapshot(identity, planes):
    return build_company_context_snapshot(
        identity=identity,
        bindings=tuple(
            _binding(identity, plane, index)
            for index, plane in enumerate(planes, start=1)
        ),
        as_of=T0 + timedelta(minutes=1),
    )


def test_new_company_is_identified_but_not_silently_filled_from_other_company():
    company = _identity("newco")
    snapshot = _snapshot(company, ())

    onboarding = assess_company_brain_onboarding(snapshot=snapshot)

    assert onboarding.stage is CompanyBrainOnboardingStage.IDENTIFIED
    assert onboarding.available_planes == ()
    assert onboarding.missing_planes == CANONICAL_COMPANY_BRAIN_PLANES
    assert onboarding.semantic_context_complete is False
    assert onboarding.cross_company_fallback_allowed is False


def test_partial_company_brain_reports_exact_missing_planes():
    company = _identity("alpha")
    snapshot = _snapshot(
        company,
        (CompanyContextPlane.KNOWLEDGE, CompanyContextPlane.POLICY),
    )

    onboarding = assess_company_brain_onboarding(
        snapshot=snapshot,
        required_planes=(
            CompanyContextPlane.KNOWLEDGE,
            CompanyContextPlane.POLICY,
            CompanyContextPlane.MEMORY,
        ),
    )

    assert onboarding.stage is CompanyBrainOnboardingStage.PARTIAL
    assert onboarding.missing_planes == (CompanyContextPlane.MEMORY,)
    assert onboarding.semantic_context_complete is False


def test_all_company_planes_can_be_context_complete_without_granting_truth_or_execution():
    company = _identity("alpha")
    snapshot = _snapshot(company, CANONICAL_COMPANY_BRAIN_PLANES)

    onboarding = assess_company_brain_onboarding(snapshot=snapshot)

    assert onboarding.stage is CompanyBrainOnboardingStage.CONTEXT_COMPLETE
    assert onboarding.missing_planes == ()
    assert onboarding.semantic_context_complete is True
    assert onboarding.firm_truth_authority_granted is False
    assert onboarding.execution_authority_granted is False


def test_runtime_request_holds_when_exact_company_plane_is_missing():
    company = _identity("alpha")
    snapshot = _snapshot(company, (CompanyContextPlane.KNOWLEDGE,))

    binding = bind_company_runtime_request(
        snapshot=snapshot,
        request_id="runtime://decision/alpha/1",
        requested_at=T0 + timedelta(minutes=2),
        required_planes=(CompanyContextPlane.KNOWLEDGE, CompanyContextPlane.POLICY),
    )

    assert binding.disposition is CompanyRuntimeDisposition.HOLD
    assert binding.blockers == ("company_brain_plane_missing:policy",)
    assert binding.execution_authority_granted is False
    assert binding.firm_truth_authority_granted is False


def test_runtime_request_proceeds_only_against_exact_snapshot_and_resolved_artifacts():
    company = _identity("alpha")
    snapshot = _snapshot(
        company,
        (CompanyContextPlane.KNOWLEDGE, CompanyContextPlane.POLICY),
    )

    binding = bind_company_runtime_request(
        snapshot=snapshot,
        request_id="runtime://reasoning/alpha/1",
        requested_at=T0 + timedelta(minutes=2),
        required_planes=(CompanyContextPlane.KNOWLEDGE, CompanyContextPlane.POLICY),
    )
    validated = validate_company_runtime_request_binding(
        binding=binding,
        snapshot=snapshot,
    )

    assert validated.disposition is CompanyRuntimeDisposition.PROCEED
    assert validated.blockers == ()
    assert len(validated.resolved_binding_fingerprints) == 2
    assert validated.company_context_snapshot_fingerprint == snapshot.fingerprint
    assert validated.company_identity_fingerprint == company.fingerprint


def test_same_tenant_other_company_snapshot_cannot_validate_runtime_binding():
    alpha = _identity("alpha")
    beta = _identity("beta")
    alpha_snapshot = _snapshot(alpha, (CompanyContextPlane.KNOWLEDGE,))
    beta_snapshot = _snapshot(beta, (CompanyContextPlane.KNOWLEDGE,))
    binding = bind_company_runtime_request(
        snapshot=alpha_snapshot,
        request_id="runtime://reasoning/alpha/2",
        requested_at=T0 + timedelta(minutes=2),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )

    with pytest.raises(ValueError, match="company_runtime_cross_company_binding"):
        validate_company_runtime_request_binding(
            binding=binding,
            snapshot=beta_snapshot,
        )


def test_profile_revision_change_invalidates_old_runtime_binding():
    old = _identity("alpha", "v1")
    current = _identity("alpha", "v2")
    old_snapshot = _snapshot(old, (CompanyContextPlane.KNOWLEDGE,))
    current_snapshot = _snapshot(current, (CompanyContextPlane.KNOWLEDGE,))
    binding = bind_company_runtime_request(
        snapshot=old_snapshot,
        request_id="runtime://reasoning/alpha/3",
        requested_at=T0 + timedelta(minutes=2),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )

    with pytest.raises(
        ValueError,
        match="company_runtime_profile_revision_mismatch|company_runtime_identity_fingerprint_mismatch",
    ):
        validate_company_runtime_request_binding(
            binding=binding,
            snapshot=current_snapshot,
        )


def test_tampered_runtime_binding_fails_integrity_rehydration():
    company = _identity("alpha")
    snapshot = _snapshot(company, (CompanyContextPlane.KNOWLEDGE,))
    binding = bind_company_runtime_request(
        snapshot=snapshot,
        request_id="runtime://reasoning/alpha/4",
        requested_at=T0 + timedelta(minutes=2),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )
    tampered = binding.model_copy(update={"company_id": "company://beta"})

    with pytest.raises(ValidationError, match="company_runtime_request_binding_fingerprint_mismatch"):
        validate_company_runtime_request_binding(
            binding=tampered,
            snapshot=snapshot,
        )


def test_runtime_request_cannot_bind_future_context_into_historical_request():
    company = _identity("alpha")
    snapshot = _snapshot(company, (CompanyContextPlane.KNOWLEDGE,))

    with pytest.raises(ValueError, match="company_runtime_request_predates_context_snapshot"):
        bind_company_runtime_request(
            snapshot=snapshot,
            request_id="runtime://historical/alpha/1",
            requested_at=T0,
            required_planes=(CompanyContextPlane.KNOWLEDGE,),
        )


def test_runtime_request_reference_cannot_retain_secret_material():
    company = _identity("alpha")
    snapshot = _snapshot(company, (CompanyContextPlane.KNOWLEDGE,))

    with pytest.raises(ValueError, match="company_runtime_request_secret_material_forbidden"):
        bind_company_runtime_request(
            snapshot=snapshot,
            request_id="runtime://alpha?token=abc123",
            requested_at=T0 + timedelta(minutes=2),
            required_planes=(CompanyContextPlane.KNOWLEDGE,),
        )
