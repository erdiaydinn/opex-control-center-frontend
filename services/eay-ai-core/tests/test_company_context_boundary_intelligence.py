from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.company_context_boundary import (
    CompanyContextPlane,
    build_company_context_binding,
    build_company_context_snapshot,
    build_company_identity,
    has_company_artifact,
    require_company_plane,
)
from app.tool_intent import (
    YS_TR_CYCLE_COUNT_SEMANTIC_REF,
    select_company_tool,
    select_tool,
)

T0 = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)
ARTIFACT_FP = "a" * 64


def _identity(company: str, revision: str = "v1"):
    return build_company_identity(
        tenant_id="tenant://shared-enterprise",
        company_id=f"company://{company}",
        company_slug=company,
        profile_revision=revision,
        environment="production",
    )


def _binding(
    identity,
    *,
    plane=CompanyContextPlane.KNOWLEDGE,
    artifact_ref="company-kpi://nsfr/v1",
    index=1,
    effective=None,
    observed=None,
    recorded=None,
):
    return build_company_context_binding(
        identity=identity,
        binding_id=f"binding://{identity.company_slug}/{index}",
        plane=plane,
        artifact_ref=artifact_ref,
        artifact_fingerprint=ARTIFACT_FP,
        effective_from=effective or T0,
        observed_at=observed or T0,
        recorded_at=recorded or T0,
        evidence_refs=(f"evidence://{identity.company_slug}/{index}",),
    )


def test_same_tenant_different_company_context_cannot_be_combined():
    alpha = _identity("alpha")
    beta = _identity("beta")
    alpha_binding = _binding(alpha)

    with pytest.raises(ValueError, match="company_context_cross_company_binding"):
        build_company_context_snapshot(
            identity=beta,
            bindings=(alpha_binding,),
            as_of=T0 + timedelta(minutes=1),
        )


def test_profile_revision_is_exact_and_old_company_semantics_do_not_bleed_forward():
    current = _identity("alpha", revision="v2")
    old = _identity("alpha", revision="v1")
    old_binding = _binding(old)

    with pytest.raises(
        ValueError,
        match="company_context_identity_fingerprint_mismatch|company_context_profile_revision_mismatch",
    ):
        build_company_context_snapshot(
            identity=current,
            bindings=(old_binding,),
            as_of=T0 + timedelta(minutes=1),
        )


def test_missing_company_knowledge_never_falls_back_to_another_company():
    alpha = _identity("alpha")
    beta = _identity("beta")
    alpha_snapshot = build_company_context_snapshot(
        identity=alpha,
        bindings=(_binding(alpha),),
        as_of=T0 + timedelta(minutes=1),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )
    beta_snapshot = build_company_context_snapshot(
        identity=beta,
        bindings=(),
        as_of=T0 + timedelta(minutes=1),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )

    assert CompanyContextPlane.KNOWLEDGE in alpha_snapshot.available_planes
    assert CompanyContextPlane.KNOWLEDGE in beta_snapshot.missing_planes
    with pytest.raises(ValueError, match="company_context_plane_missing:knowledge"):
        require_company_plane(
            snapshot=beta_snapshot,
            plane=CompanyContextPlane.KNOWLEDGE,
        )


@pytest.mark.parametrize(
    "plane",
    [
        CompanyContextPlane.MEMORY,
        CompanyContextPlane.CAPABILITY,
        CompanyContextPlane.CALIBRATION,
        CompanyContextPlane.POLICY,
        CompanyContextPlane.MODEL_PROFILE,
        CompanyContextPlane.TRUTH_BINDING,
    ],
)
def test_private_company_planes_reject_cross_company_reuse(plane):
    alpha = _identity("alpha")
    beta = _identity("beta")
    binding = _binding(
        alpha,
        plane=plane,
        artifact_ref=f"company-artifact://alpha/{plane.value}",
    )

    with pytest.raises(ValueError, match="company_context_cross_company_binding"):
        build_company_context_snapshot(
            identity=beta,
            bindings=(binding,),
            as_of=T0 + timedelta(minutes=1),
        )


def test_future_recorded_or_future_effective_company_binding_does_not_leak_into_history():
    alpha = _identity("alpha")
    future_recorded = _binding(
        alpha,
        index=1,
        observed=T0,
        recorded=T0 + timedelta(hours=2),
    )
    future_effective = _binding(
        alpha,
        index=2,
        artifact_ref="company-policy://alpha/future",
        effective=T0 + timedelta(hours=3),
        observed=T0,
        recorded=T0,
    )

    historical = build_company_context_snapshot(
        identity=alpha,
        bindings=(future_recorded, future_effective),
        as_of=T0 + timedelta(hours=1),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )

    assert historical.bindings == ()
    assert historical.missing_planes == (CompanyContextPlane.KNOWLEDGE,)


def test_tampered_identity_and_binding_fail_before_company_context_use():
    alpha = _identity("alpha")
    binding = _binding(alpha)

    tampered_identity = alpha.model_copy(update={"company_id": "company://beta"})
    with pytest.raises(ValidationError, match="company_identity_fingerprint_mismatch"):
        build_company_context_snapshot(
            identity=tampered_identity,
            bindings=(),
            as_of=T0,
        )

    tampered_binding = binding.model_copy(update={"company_id": "company://beta"})
    with pytest.raises(ValidationError, match="company_context_binding_fingerprint_mismatch"):
        build_company_context_snapshot(
            identity=alpha,
            bindings=(tampered_binding,),
            as_of=T0,
        )


def test_company_context_never_grants_truth_execution_or_shared_distillation_authority():
    alpha = _identity("alpha")
    binding = _binding(alpha)
    snapshot = build_company_context_snapshot(
        identity=alpha,
        bindings=(binding,),
        as_of=T0,
    )

    assert binding.cross_company_reuse_allowed is False
    assert binding.shared_model_distillation_allowed is False
    assert binding.firm_truth_authority_granted is False
    assert binding.execution_authority_granted is False
    assert snapshot.cross_company_fallback_allowed is False
    assert snapshot.firm_truth_authority_granted is False
    assert snapshot.execution_authority_granted is False


def test_secret_bearing_company_reference_is_rejected():
    alpha = _identity("alpha")
    with pytest.raises(ValueError, match="company_context_secret_bearing_reference_forbidden"):
        _binding(
            alpha,
            artifact_ref="company-source://alpha?token=abc123",
        )


def test_one_hundred_company_partitions_do_not_cross_resolve_artifacts():
    identities = tuple(_identity(f"company-{index}") for index in range(100))
    snapshots = tuple(
        build_company_context_snapshot(
            identity=identity,
            bindings=(
                _binding(
                    identity,
                    artifact_ref=f"company-kpi://{identity.company_slug}/orders",
                    index=index + 1,
                ),
            ),
            as_of=T0,
        )
        for index, identity in enumerate(identities)
    )

    for index, snapshot in enumerate(snapshots):
        own = f"company-kpi://company-{index}/orders"
        other = f"company-kpi://company-{(index + 1) % 100}/orders"
        assert has_company_artifact(
            snapshot=snapshot,
            plane=CompanyContextPlane.KNOWLEDGE,
            artifact_ref=own,
        )
        assert not has_company_artifact(
            snapshot=snapshot,
            plane=CompanyContextPlane.KNOWLEDGE,
            artifact_ref=other,
        )


def test_public_tool_selector_never_applies_ys_tr_company_semantics():
    result = select_tool("Bu hafta sayım uyum oranımız nedir?")

    assert result.tool == "ops_kpi_query"
    assert result.confidence == 0.84
    assert "YS_TR" not in result.rationale
    assert result.execution_allowed is False


def test_ys_tr_semantics_require_exact_trusted_company_artifact():
    ys = _identity("ys-tr")
    other = _identity("other-company")
    ys_binding = _binding(
        ys,
        artifact_ref=YS_TR_CYCLE_COUNT_SEMANTIC_REF,
    )
    ys_snapshot = build_company_context_snapshot(
        identity=ys,
        bindings=(ys_binding,),
        as_of=T0,
    )
    other_snapshot = build_company_context_snapshot(
        identity=other,
        bindings=(),
        as_of=T0,
    )

    governed = select_company_tool(
        "Bu hafta sayım uyum oranımız nedir?",
        company_context=ys_snapshot,
    )
    generic = select_company_tool(
        "Bu hafta sayım uyum oranımız nedir?",
        company_context=other_snapshot,
    )

    assert governed.tool == "ops_kpi_query"
    assert governed.confidence == 0.97
    assert "YS_TR" in governed.rationale
    assert generic.tool == "ops_kpi_query"
    assert generic.confidence == 0.84
    assert "YS_TR" not in generic.rationale
    assert governed.execution_allowed is False
