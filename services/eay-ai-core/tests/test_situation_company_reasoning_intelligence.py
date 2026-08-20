from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.company_brain_runtime import bind_company_runtime_request
from app.company_context_boundary import (
    build_company_context_binding,
    build_company_context_snapshot,
    build_company_identity,
)
from app.company_reasoning_runtime import (
    COMPANY_REASONING_REQUIRED_PLANES,
    CompanyReasoningRuntime,
)
from app.global_lane_lease_broker import GlobalLaneLeaseAdmission
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
from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.multi_objective_swarm_runtime import MultiObjectiveExecutionRound
from app.objective_decomposition_admission import (
    ObjectiveDecompositionPolicy,
    ObjectiveDecompositionProposal,
    ProposedObjectiveLane,
)
from app.paid_token_engine_gateway import PaidTokenExecutionContext
from app.parallel_mission_orchestration import (
    ParallelLaneDisposition,
    ParallelLaneResult,
    ParallelMissionLane,
    ParallelMissionRound,
)
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.situation_company_reasoning import (
    SituationCompanyReasoningRuntime,
    situation_reasoning_task_id,
)
from app.situation_detection import SituationCandidate, detect_situations
from app.situation_objective_admission import (
    SituationObjectiveRule,
    admit_situation_driven_objective,
)
from app.strong_reasoning_runtime import StrongReasoningExecution, StrongReasoningStatus
from app.swarm_execution_telemetry import build_swarm_execution_telemetry
from app.swarm_worker_registry import SwarmLaneRequirement, SwarmWorkerClass


NOW = datetime(2026, 8, 20, 5, 30, tzinfo=timezone.utc)
TENANT = "YS_TR"
OBJECT = "store://fulya"
REVIEW_REF = "review://situation/orders-weather-otp/v1"


def _execution_round() -> MultiObjectiveExecutionRound:
    objective = ParallelMissionRound(
        objective_ref="objective://ops",
        tenant_id=TENANT,
        selected_lane_ids=("orders-read",),
        results=(
            ParallelLaneResult(
                lane_id="orders-read",
                disposition=ParallelLaneDisposition.DEFERRED,
                blockers=("live_company_truth_receipt_missing:read-orders",),
            ),
        ),
    )
    return MultiObjectiveExecutionRound(
        admission=GlobalLaneLeaseAdmission(selected=(), deferred={}, issued_leases=()),
        objective_rounds=(objective,),
        deferred={
            "objective://inventory::write": (
                "global_lane_resource_lease_conflict:store://fulya",
            ),
        },
        active_leases_after_round=(),
    )


def _event(
    event_id: str,
    event_type: str,
    authority: TimelineAuthorityClass,
    at: datetime,
):
    kind = (
        TimelineEventKind.EXTERNAL_CONTEXT
        if authority is TimelineAuthorityClass.VERIFIED_EXTERNAL
        else TimelineEventKind.COMPANY_ASSERTION
    )
    return build_timeline_event(
        event_id=event_id,
        event_type=event_type,
        event_kind=kind,
        source_ref=f"source://{event_id}",
        tenant_id=TENANT,
        occurred_at=at - timedelta(seconds=1),
        observed_at=at,
        data_ref=f"data://{event_id}",
        authority_class=authority,
        confidence=0.97,
        object_relations=(
            TimelineObjectRelation(
                object_ref=OBJECT,
                object_kind=TimelineObjectKind.LOCATION,
                qualifier=TimelineObjectQualifier.AFFECTED,
            ),
        ),
        evidence_refs=(f"evidence://{event_id}",),
    )


def _situation(at: datetime = NOW, suffix: str = "a") -> SituationCandidate:
    telemetry = build_swarm_execution_telemetry(
        execution_round=_execution_round(),
        tenant_id=TENANT,
        observed_at=at,
    )
    events = (
        _event(
            f"orders-{suffix}",
            "eay.company.orders.spike",
            TimelineAuthorityClass.VERIFIED_COMPANY,
            at,
        ),
        _event(
            f"weather-{suffix}",
            "eay.external.weather.rain",
            TimelineAuthorityClass.VERIFIED_EXTERNAL,
            at,
        ),
        _event(
            f"otp-{suffix}",
            "eay.company.otp.degraded",
            TimelineAuthorityClass.GOVERNED_OPERATIONAL,
            at,
        ),
    )
    situations = detect_situations(
        events=events,
        telemetry=telemetry,
        tenant_id=TENANT,
        now=at,
    )
    assert len(situations) == 1
    return situations[0]


def _proposal(candidate: SituationCandidate) -> ObjectiveDecompositionProposal:
    step = MissionStep(
        step_id="read-orders",
        description="Investigate the admitted situation before reasoning",
    )
    definition = MissionDefinition(
        mission_id=f"mission-situation-{candidate.fingerprint[:12]}",
        objective="Investigate a verified company situation",
        tenant_id=TENANT,
        steps=(step,),
    )
    lane = ParallelMissionLane(
        lane_id="situation-company-read",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=candidate.detected_at),
        specs=(
            MissionExecutionSpec(
                step_id="read-orders",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref="company.orders.read",
            ),
        ),
        priority=90,
    )
    return ObjectiveDecompositionProposal(
        objective_ref=f"objective://situation/{candidate.fingerprint[:16]}",
        tenant_id=TENANT,
        lanes=(
            ProposedObjectiveLane(
                lane=lane,
                profile=ParallelLaneSchedulingProfile(
                    lane_id=lane.lane_id,
                    scheduling_class=LaneSchedulingClass.COMPANY_READ,
                    estimated_cost_units=5,
                    concurrency_weight=1,
                    shedable=True,
                    preemptible=True,
                ),
                requirement=SwarmLaneRequirement(
                    lane_id=lane.lane_id,
                    required_worker_classes=(SwarmWorkerClass.COMPANY_READ,),
                    required_capability_refs=("company.orders.read",),
                ),
                evidence_refs=(f"situation-candidate://{candidate.fingerprint}",),
            ),
        ),
        decomposition_evidence_refs=(
            f"situation-candidate://{candidate.fingerprint}",
            REVIEW_REF,
        ),
        max_parallel_lanes=1,
    )


def _admission(candidate: SituationCandidate):
    return admit_situation_driven_objective(
        candidate=candidate,
        proposal=_proposal(candidate),
        rule=SituationObjectiveRule(
            rule_ref="situation-rule://orders-weather-otp/v1",
            tenant_id=TENANT,
            objective_ref_prefix="objective://situation/",
            required_domains=("orders", "otp", "weather"),
            review_evidence_ref=REVIEW_REF,
        ),
        decomposition_policy=ObjectiveDecompositionPolicy(
            max_lanes=8,
            max_mutating_lanes=0,
            max_total_cost_units=100,
            max_total_concurrency_weight=16,
        ),
        now=candidate.detected_at + timedelta(seconds=30),
    )


def _snapshot(*, tenant: str = TENANT, company: str = "yemeksepeti"):
    identity = build_company_identity(
        tenant_id=tenant,
        company_id=f"company://{company}",
        company_slug=company,
        profile_revision="v1",
        environment="production",
    )
    bindings = tuple(
        build_company_context_binding(
            identity=identity,
            binding_id=f"binding://{company}/{plane.value}",
            plane=plane,
            artifact_ref=f"artifact://{company}/{plane.value}/v1",
            artifact_fingerprint="a" * 64,
            effective_from=NOW,
            observed_at=NOW,
            recorded_at=NOW,
            evidence_refs=(f"evidence://{company}/{plane.value}",),
        )
        for plane in COMPANY_REASONING_REQUIRED_PLANES
    )
    return build_company_context_snapshot(
        identity=identity,
        bindings=bindings,
        as_of=NOW + timedelta(minutes=1),
        required_planes=COMPANY_REASONING_REQUIRED_PLANES,
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


class _FakeReasoningRuntime:
    def __init__(self):
        self.calls = 0
        self.last_allowed_evidence_refs = ()

    async def execute(self, **kwargs):
        self.calls += 1
        self.last_allowed_evidence_refs = kwargs["allowed_evidence_refs"]
        return StrongReasoningExecution(
            task_id=kwargs["task"].task_id,
            status=StrongReasoningStatus.LOCAL_RESULT,
            plan_mode=kwargs["plan"].mode,
            engine_evidence=(),
        )


def _inputs(candidate: SituationCandidate, admission, snapshot):
    task_id = situation_reasoning_task_id(
        candidate=candidate,
        admission=admission,
    )
    task = IntelligenceTask(
        task_id=task_id,
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        external_processing_authorized=False,
    )
    binding = bind_company_runtime_request(
        snapshot=snapshot,
        request_id=task_id,
        requested_at=NOW + timedelta(minutes=2),
        required_planes=COMPANY_REASONING_REQUIRED_PLANES,
    )
    allowed = tuple(
        dict.fromkeys(
            (
                *candidate.evidence_refs,
                f"situation-candidate://{candidate.fingerprint}",
                *admission.admitted.proposal_evidence_refs,
                "evidence://company/reasoning-support",
            )
        )
    )
    context = PaidTokenExecutionContext(
        subject_user_ref="user://operator",
        tenant_ref=TENANT,
        billing_cycle_ref="billing-cycle://2026-08",
        requested_at=NOW + timedelta(minutes=2),
    )
    return task, binding, allowed, context


def _run(
    underlying,
    *,
    candidate,
    admission,
    snapshot,
    task,
    binding,
    allowed,
    context,
):
    return asyncio.run(
        SituationCompanyReasoningRuntime(
            company_reasoning_runtime=CompanyReasoningRuntime(
                reasoning_runtime=underlying
            )
        ).execute(
            candidate=candidate,
            admission=admission,
            company_snapshot=snapshot,
            company_binding=binding,
            plan=_plan(),
            information_gain=_information_gain(),
            task=task,
            prompt="Explain the admitted operational situation without claiming causality.",
            claim_keys=("claim://situation/assessment",),
            allowed_evidence_refs=allowed,
            context=context,
        )
    )


def test_admitted_situation_executes_company_bound_reasoning_once_and_stays_non_authoritative():
    candidate = _situation()
    admission = _admission(candidate)
    snapshot = _snapshot()
    task, binding, allowed, context = _inputs(candidate, admission, snapshot)
    underlying = _FakeReasoningRuntime()

    result = _run(
        underlying,
        candidate=candidate,
        admission=admission,
        snapshot=snapshot,
        task=task,
        binding=binding,
        allowed=allowed,
        context=context,
    )

    assert underlying.calls == 1
    assert result.situation_fingerprint == candidate.fingerprint
    assert result.objective_ref == admission.objective_ref
    assert result.task_id == task.task_id
    assert result.company_id == snapshot.identity.company_id
    assert f"situation-candidate://{candidate.fingerprint}" in underlying.last_allowed_evidence_refs
    assert result.causal_claim_proven is False
    assert result.firm_truth_authority_granted is False
    assert result.replanning_authority_granted is False
    assert result.execution_authority_granted is False


def test_different_situation_cannot_reuse_an_existing_admission_before_model_call():
    first = _situation(NOW, "first")
    second = _situation(NOW + timedelta(minutes=1), "second")
    admission = _admission(first)
    snapshot = _snapshot()
    task, binding, allowed, context = _inputs(first, admission, snapshot)
    underlying = _FakeReasoningRuntime()

    with pytest.raises(
        ValueError,
        match="situation_company_reasoning_admission_candidate_mismatch",
    ):
        _run(
            underlying,
            candidate=second,
            admission=admission,
            snapshot=snapshot,
            task=task,
            binding=binding,
            allowed=allowed,
            context=context,
        )

    assert underlying.calls == 0


def test_missing_situation_root_evidence_fails_before_model_call():
    candidate = _situation()
    admission = _admission(candidate)
    snapshot = _snapshot()
    task, binding, allowed, context = _inputs(candidate, admission, snapshot)
    underlying = _FakeReasoningRuntime()
    missing = tuple(
        ref
        for ref in allowed
        if ref != f"situation-candidate://{candidate.fingerprint}"
    )

    with pytest.raises(
        ValueError,
        match="situation_company_reasoning_required_evidence_missing",
    ):
        _run(
            underlying,
            candidate=candidate,
            admission=admission,
            snapshot=snapshot,
            task=task,
            binding=binding,
            allowed=missing,
            context=context,
        )

    assert underlying.calls == 0


def test_generic_company_reasoning_task_cannot_impersonate_situation_reasoning():
    candidate = _situation()
    admission = _admission(candidate)
    snapshot = _snapshot()
    _, _, allowed, context = _inputs(candidate, admission, snapshot)
    generic_task = IntelligenceTask(
        task_id="reasoning://generic/company",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
    )
    generic_binding = bind_company_runtime_request(
        snapshot=snapshot,
        request_id=generic_task.task_id,
        requested_at=NOW + timedelta(minutes=2),
        required_planes=COMPANY_REASONING_REQUIRED_PLANES,
    )
    underlying = _FakeReasoningRuntime()

    with pytest.raises(
        ValueError,
        match="situation_company_reasoning_task_binding_mismatch",
    ):
        _run(
            underlying,
            candidate=candidate,
            admission=admission,
            snapshot=snapshot,
            task=generic_task,
            binding=generic_binding,
            allowed=allowed,
            context=context,
        )

    assert underlying.calls == 0


def test_cross_tenant_company_snapshot_is_rejected_before_model_call():
    candidate = _situation()
    admission = _admission(candidate)
    valid_snapshot = _snapshot()
    task, binding, allowed, context = _inputs(candidate, admission, valid_snapshot)
    other_snapshot = _snapshot(tenant="tenant://other", company="other")
    underlying = _FakeReasoningRuntime()

    with pytest.raises(
        ValueError,
        match="situation_company_reasoning_company_tenant_mismatch",
    ):
        _run(
            underlying,
            candidate=candidate,
            admission=admission,
            snapshot=other_snapshot,
            task=task,
            binding=binding,
            allowed=allowed,
            context=context,
        )

    assert underlying.calls == 0
