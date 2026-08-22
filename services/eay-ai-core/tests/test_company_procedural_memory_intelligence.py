from datetime import datetime, timedelta, timezone

import pytest

from app.company_context_boundary import (
    CompanyContextPlane,
    build_company_context_binding,
    build_company_context_snapshot,
    build_company_identity,
)
from app.procedural_memory import (
    ProcedureDemonstration,
    ProcedureStatus,
    ProcedureStep,
    ProcedureStepKind,
    compile_company_procedure,
    compile_procedure,
    procedure_step_fingerprint,
)

T0 = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
ENV = "b" * 64
ARTIFACT_FP = "c" * 64


def _identity(company: str, revision: str = "v1"):
    return build_company_identity(
        tenant_id="tenant://multi-company",
        company_id=f"company://{company}",
        company_slug=company,
        profile_revision=revision,
        environment="production",
    )


def _context(identity, planes=(CompanyContextPlane.MEMORY, CompanyContextPlane.CAPABILITY)):
    bindings = tuple(
        build_company_context_binding(
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
        for index, plane in enumerate(planes, start=1)
    )
    return build_company_context_snapshot(
        identity=identity,
        bindings=bindings,
        as_of=T0 + timedelta(minutes=1),
    )


def _steps():
    return (
        ProcedureStep(
            step_id="read",
            kind=ProcedureStepKind.API,
            operation_ref="capability://inventory.read-stock",
        ),
        ProcedureStep(
            step_id="write",
            kind=ProcedureStepKind.API,
            operation_ref="candidate://inventory.adjust-stock",
            side_effect=True,
            expected_effect_ref="stock://decrement",
            verifier_ref="capability://inventory.read-stock",
        ),
        ProcedureStep(
            step_id="verify",
            kind=ProcedureStepKind.READBACK,
            operation_ref="capability://inventory.read-stock",
        ),
    )


def _demo(identity, demo_id: str, **overrides):
    payload = dict(
        demonstration_id=demo_id,
        tenant_id=identity.tenant_id,
        company_id=identity.company_id,
        company_profile_revision=identity.profile_revision,
        company_identity_fingerprint=identity.fingerprint,
        capability_name="inventory.adjust-stock",
        observed_at=T0,
        step_fingerprint=procedure_step_fingerprint(_steps()),
        successful=True,
        effect_verified=True,
        ambiguous_outcome=False,
        environment_fingerprint=ENV,
        evidence_refs=(f"evidence://{identity.company_slug}/{demo_id}",),
    )
    payload.update(overrides)
    return ProcedureDemonstration(**payload)


def test_company_procedure_compiles_only_with_exact_memory_and_capability_context():
    alpha = _identity("alpha")
    context = _context(alpha)

    capability = compile_company_procedure(
        company_context=context,
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[_demo(alpha, "one"), _demo(alpha, "two")],
    )

    assert capability.status is ProcedureStatus.VALIDATED
    assert capability.company_id == alpha.company_id
    assert capability.company_profile_revision == alpha.profile_revision
    assert capability.company_identity_fingerprint == alpha.fingerprint
    assert capability.demonstrations == ("one", "two")


def test_generic_compiler_refuses_to_strip_company_scope_from_company_demonstrations():
    alpha = _identity("alpha")

    with pytest.raises(
        ValueError,
        match="procedure_company_bound_demonstration_requires_company_compile",
    ):
        compile_procedure(
            tenant_id=alpha.tenant_id,
            capability_name="inventory.adjust-stock",
            steps=_steps(),
            demonstrations=[_demo(alpha, "one"), _demo(alpha, "two")],
        )


def test_same_tenant_other_company_demonstration_cannot_enter_company_procedure():
    alpha = _identity("alpha")
    beta = _identity("beta")
    context = _context(alpha)

    with pytest.raises(ValueError, match="procedure_company_demonstration_scope_mismatch"):
        compile_company_procedure(
            company_context=context,
            capability_name="inventory.adjust-stock",
            steps=_steps(),
            demonstrations=[_demo(alpha, "one"), _demo(beta, "two")],
        )


def test_unscoped_legacy_demonstration_cannot_enter_company_procedure():
    alpha = _identity("alpha")
    context = _context(alpha)
    unscoped = ProcedureDemonstration(
        demonstration_id="legacy",
        tenant_id=alpha.tenant_id,
        capability_name="inventory.adjust-stock",
        observed_at=T0,
        step_fingerprint=procedure_step_fingerprint(_steps()),
        successful=True,
        effect_verified=True,
        environment_fingerprint=ENV,
        evidence_refs=("evidence://legacy",),
    )

    with pytest.raises(ValueError, match="procedure_company_demonstration_scope_mismatch"):
        compile_company_procedure(
            company_context=context,
            capability_name="inventory.adjust-stock",
            steps=_steps(),
            demonstrations=[unscoped],
        )


def test_profile_revision_change_requires_fresh_company_procedure_evidence():
    old = _identity("alpha", "v1")
    current = _identity("alpha", "v2")
    current_context = _context(current)

    with pytest.raises(ValueError, match="procedure_company_demonstration_scope_mismatch"):
        compile_company_procedure(
            company_context=current_context,
            capability_name="inventory.adjust-stock",
            steps=_steps(),
            demonstrations=[_demo(old, "one"), _demo(old, "two")],
        )


def test_company_procedure_requires_memory_plane():
    alpha = _identity("alpha")
    incomplete = _context(alpha, planes=(CompanyContextPlane.CAPABILITY,))

    with pytest.raises(ValueError, match="company_context_plane_missing:memory"):
        compile_company_procedure(
            company_context=incomplete,
            capability_name="inventory.adjust-stock",
            steps=_steps(),
            demonstrations=[_demo(alpha, "one"), _demo(alpha, "two")],
        )


def test_company_procedure_requires_capability_plane():
    alpha = _identity("alpha")
    incomplete = _context(alpha, planes=(CompanyContextPlane.MEMORY,))

    with pytest.raises(ValueError, match="company_context_plane_missing:capability"):
        compile_company_procedure(
            company_context=incomplete,
            capability_name="inventory.adjust-stock",
            steps=_steps(),
            demonstrations=[_demo(alpha, "one"), _demo(alpha, "two")],
        )


def test_same_tenant_same_workflow_gets_distinct_capability_identity_per_company():
    alpha = _identity("alpha")
    beta = _identity("beta")
    alpha_capability = compile_company_procedure(
        company_context=_context(alpha),
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[_demo(alpha, "one"), _demo(alpha, "two")],
    )
    beta_capability = compile_company_procedure(
        company_context=_context(beta),
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[_demo(beta, "one"), _demo(beta, "two")],
    )

    assert alpha_capability.tenant_id == beta_capability.tenant_id
    assert alpha_capability.capability_name == beta_capability.capability_name
    assert alpha_capability.capability_id != beta_capability.capability_id
    assert alpha_capability.company_identity_fingerprint != beta_capability.company_identity_fingerprint
