import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.company_brain_runtime import bind_company_runtime_request
from app.company_context_boundary import (
    CompanyContextPlane,
    build_company_context_binding,
    build_company_context_snapshot,
    build_company_identity,
)
from app.company_reasoning_runtime import (
    COMPANY_REASONING_REQUIRED_PLANES,
    CompanyReasoningRuntime,
)
from app.intelligence_router import (
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.intelligence_supremacy import (
    InformationGainPlan,
    ReasoningMode,
    ReasoningRisk,
    ReasoningStrengthPlan,
)
from app.paid_token_engine_gateway import PaidTokenExecutionContext
from app.strong_reasoning_runtime import (
    StrongReasoningExecution,
    StrongReasoningStatus,
)

T0 = datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc)
ARTIFACT_FP = "a" * 64
EVIDENCE = "evidence://company/alpha/knowledge"


def _identity(company: str, *, tenant: str = "tenant://shared", revision: str = "v1"):
    return build_company_identity(
        tenant_id=tenant,
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


def _task(task_id: str = "reasoning://alpha/executive/1"):
    return IntelligenceTask(
        task_id=task_id,
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        external_processing_authorized=False,
    )


def _plan():
    return ReasoningStrengthPlan(
        risk=ReasoningRisk.HIGH,
        mode=ReasoningMode.LOCAL_SINGLE,
        unresolved_gap_count=0,
        calibrated_confidence_multiplier=1.0,
        local_council_required=False,
        frontier_escalation_candidate=False,
        requires_platform_admin_paid_grant=False,
        human_review_required=False,
        blockers=(),
    )


def _information_gain():
    return InformationGainPlan(
        gap_ids=(),
        ranked=(),
        selected_investigation_ids=(),
        total_selected_cost_units=0.0,
        unresolved_gap_ids=(),
    )


def _context(tenant: str = "tenant://shared"):
    return PaidTokenExecutionContext(
        subject_user_ref="user://erdi",
        tenant_ref=tenant,
        billing_cycle_ref="billing-cycle://2026-08",
        requested_at=T0 + timedelta(minutes=2),
    )


def _runtime_binding(snapshot, task_id: str = "reasoning://alpha/executive/1"):
    return bind_company_runtime_request(
        snapshot=snapshot,
        request_id=task_id,
        requested_at=T0 + timedelta(minutes=2),
        required_planes=COMPANY_REASONING_REQUIRED_PLANES,
    )


class _FakeReasoningRuntime:
    def __init__(self):
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        return StrongReasoningExecution(
            task_id=kwargs["task"].task_id,
            status=StrongReasoningStatus.LOCAL_RESULT,
            plan_mode=kwargs["plan"].mode,
            engine_evidence=(),
        )


def _execute(
    runtime,
    *,
    snapshot,
    binding,
    task=None,
    context=None,
):
    return asyncio.run(
        CompanyReasoningRuntime(reasoning_runtime=runtime).execute(
            company_snapshot=snapshot,
            company_binding=binding,
            plan=_plan(),
            information_gain=_information_gain(),
            task=task or _task(),
            prompt="Assess the company-specific situation.",
            claim_keys=("claim://company-situation",),
            allowed_evidence_refs=(EVIDENCE,),
            context=context or _context(),
        )
    )


def test_valid_company_binding_executes_once_and_seals_company_scope():
    identity = _identity("alpha")
    snapshot = _snapshot(identity, COMPANY_REASONING_REQUIRED_PLANES)
    binding = _runtime_binding(snapshot)
    underlying = _FakeReasoningRuntime()

    result = _execute(underlying, snapshot=snapshot, binding=binding)

    assert underlying.calls == 1
    assert result.tenant_id == identity.tenant_id
    assert result.company_id == identity.company_id
    assert result.profile_revision == identity.profile_revision
    assert result.company_identity_fingerprint == identity.fingerprint
    assert result.company_context_snapshot_fingerprint == snapshot.fingerprint
    assert result.company_runtime_binding_fingerprint == binding.fingerprint
    assert result.firm_truth_authority_granted is False
    assert result.execution_authority_granted is False
    assert result.cross_company_fallback_allowed is False


def test_missing_model_profile_holds_before_any_reasoning_call():
    identity = _identity("alpha")
    snapshot = _snapshot(identity, (CompanyContextPlane.KNOWLEDGE,))
    binding = _runtime_binding(snapshot)
    underlying = _FakeReasoningRuntime()

    with pytest.raises(ValueError, match="company_reasoning_company_brain_not_ready"):
        _execute(underlying, snapshot=snapshot, binding=binding)

    assert underlying.calls == 0


def test_binding_that_omits_required_company_reasoning_plane_fails_before_model_call():
    identity = _identity("alpha")
    snapshot = _snapshot(identity, COMPANY_REASONING_REQUIRED_PLANES)
    binding = bind_company_runtime_request(
        snapshot=snapshot,
        request_id=_task().task_id,
        requested_at=T0 + timedelta(minutes=2),
        required_planes=(CompanyContextPlane.KNOWLEDGE,),
    )
    underlying = _FakeReasoningRuntime()

    with pytest.raises(ValueError, match="company_reasoning_required_planes_not_bound"):
        _execute(underlying, snapshot=snapshot, binding=binding)

    assert underlying.calls == 0


def test_same_tenant_other_company_cannot_reuse_reasoning_binding():
    alpha = _identity("alpha")
    beta = _identity("beta")
    alpha_snapshot = _snapshot(alpha, COMPANY_REASONING_REQUIRED_PLANES)
    beta_snapshot = _snapshot(beta, COMPANY_REASONING_REQUIRED_PLANES)
    binding = _runtime_binding(alpha_snapshot)
    underlying = _FakeReasoningRuntime()

    with pytest.raises(ValueError, match="company_runtime_cross_company_binding"):
        _execute(underlying, snapshot=beta_snapshot, binding=binding)

    assert underlying.calls == 0


def test_profile_revision_change_rejects_old_reasoning_binding():
    old = _identity("alpha", revision="v1")
    current = _identity("alpha", revision="v2")
    old_snapshot = _snapshot(old, COMPANY_REASONING_REQUIRED_PLANES)
    current_snapshot = _snapshot(current, COMPANY_REASONING_REQUIRED_PLANES)
    binding = _runtime_binding(old_snapshot)
    underlying = _FakeReasoningRuntime()

    with pytest.raises(
        ValueError,
        match=(
            "company_runtime_profile_revision_mismatch|"
            "company_runtime_identity_fingerprint_mismatch"
        ),
    ):
        _execute(underlying, snapshot=current_snapshot, binding=binding)

    assert underlying.calls == 0


def test_task_id_must_match_exact_company_request_binding():
    identity = _identity("alpha")
    snapshot = _snapshot(identity, COMPANY_REASONING_REQUIRED_PLANES)
    binding = _runtime_binding(snapshot)
    underlying = _FakeReasoningRuntime()

    with pytest.raises(ValueError, match="company_reasoning_task_binding_mismatch"):
        _execute(
            underlying,
            snapshot=snapshot,
            binding=binding,
            task=_task("reasoning://alpha/executive/other"),
        )

    assert underlying.calls == 0


def test_paid_execution_context_cannot_cross_tenant_before_provider_call():
    identity = _identity("alpha")
    snapshot = _snapshot(identity, COMPANY_REASONING_REQUIRED_PLANES)
    binding = _runtime_binding(snapshot)
    underlying = _FakeReasoningRuntime()

    with pytest.raises(
        ValueError,
        match="company_reasoning_paid_context_tenant_mismatch",
    ):
        _execute(
            underlying,
            snapshot=snapshot,
            binding=binding,
            context=_context("tenant://other"),
        )

    assert underlying.calls == 0


def test_tampered_company_reasoning_binding_is_rejected_before_model_call():
    identity = _identity("alpha")
    snapshot = _snapshot(identity, COMPANY_REASONING_REQUIRED_PLANES)
    binding = _runtime_binding(snapshot)
    tampered = binding.model_copy(update={"company_id": "company://beta"})
    underlying = _FakeReasoningRuntime()

    with pytest.raises(
        ValidationError,
        match="company_runtime_request_binding_fingerprint_mismatch",
    ):
        _execute(underlying, snapshot=snapshot, binding=tampered)

    assert underlying.calls == 0
