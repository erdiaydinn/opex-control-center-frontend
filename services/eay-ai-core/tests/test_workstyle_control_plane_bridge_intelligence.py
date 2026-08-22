from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.hierarchical_agent_delegation import (
    AgentCandidate,
    AgentDelegationPolicy,
    AgentDelegationRequest,
    admit_agent_delegation,
)
from app.parallel_mission_scheduler import LaneSchedulingClass
from app.specialist_mastery_registry import (
    MasteryTier,
    SpecialistDomain,
    SpecialistScorecard,
    admit_specialist_mastery,
    build_specialist_evidence,
)
from app.swarm_worker_registry import SwarmWorkerClass
from app.workstyle_agent_os import (
    SpecialistRequirement,
    WorkCapability,
    WorkTaskSpec,
    admit_work_plan,
    build_work_plan,
)
from app.workstyle_control_plane_bridge import compose_work_control_plane

NOW = datetime(2026, 8, 21, 7, 0, tzinfo=UTC)
SPECIALIST_ID = "legal-master-1"


def _mastery():
    score = SpecialistScorecard(
        factuality=0.995,
        currentness=0.995,
        source_quality=0.995,
        citation_completeness=0.995,
        falsification_performance=0.995,
        calibration=0.995,
        tool_correctness=0.995,
        domain_benchmark=0.995,
        authority_adherence=0.995,
        adversarial_robustness=0.995,
    )
    evidence = tuple(
        build_specialist_evidence(
            specialist_id=SPECIALIST_ID,
            domain=SpecialistDomain.LEGAL,
            benchmark_id=f"legal-{index}",
            benchmark_version="v1",
            evaluated_cases=200,
            observed_at=NOW - timedelta(days=1),
            scorecard=score,
            evidence_refs=(f"evidence://legal/{index}",),
            production_shaped=True,
            independent_evaluator=True,
            reproducible=True,
        )
        for index in range(3)
    )
    decision = admit_specialist_mastery(
        specialist_id=SPECIALIST_ID,
        domain=SpecialistDomain.LEGAL,
        evidence=evidence,
        now=NOW,
    )
    assert decision.admitted_tier is MasteryTier.MASTER
    return decision


def _plan(objective: str = "Research the current Turkish legal position"):
    return build_work_plan(
        tenant_id="tenant-a",
        company_id="company-a",
        session_id="work-legal",
        revision=1,
        objective=objective,
        tasks=(
            WorkTaskSpec(
                task_id="legal-research",
                objective=objective,
                required_capabilities=(
                    WorkCapability.DEEP_RESEARCH,
                    WorkCapability.DOMAIN_EXPERT,
                ),
                specialist_requirements=(
                    SpecialistRequirement(
                        domain=SpecialistDomain.LEGAL,
                        minimum_tier=MasteryTier.MASTER,
                    ),
                ),
            ),
        ),
        created_at=NOW,
    )


def _work_admission(plan, mastery):
    return admit_work_plan(
        plan=plan,
        available_capabilities=(
            WorkCapability.DEEP_RESEARCH,
            WorkCapability.DOMAIN_EXPERT,
        ),
        mastery_decisions=(mastery,),
        approvals=(),
        now=NOW,
    )


def _delegation(plan, *, agent_id: str = SPECIALIST_ID, company_scope: bool = True):
    scope = ("company:company-a",) if company_scope else ()
    request = AgentDelegationRequest(
        objective_ref=plan.fingerprint,
        tenant_id="tenant-a",
        parent_session_ref="work-legal",
        parent_agent_id="jarvis-work-controller",
        delegation_depth=1,
        requested_agent_count=1,
        required_worker_classes=(SwarmWorkerClass.LEGAL,),
        required_capability_refs=("work:deep_research", "work:domain_expert"),
        allowed_authority_scope_refs=("company:company-a",),
        subtree_cost_budget=1000,
        subtree_transition_budget=100,
        user_command_evidence_ref="evidence://user/work-legal",
        cancellation_token_ref="cancel://work-legal",
    )
    candidate = AgentCandidate(
        agent_id=agent_id,
        tenant_id="tenant-a",
        worker_class=SwarmWorkerClass.LEGAL,
        scheduling_classes=(LaneSchedulingClass.RESEARCH,),
        capability_refs=("work:deep_research", "work:domain_expert"),
        provider_key="local-legal-runtime",
        attestation_ref="attestation://legal-master-1",
        attestation_fingerprint="a" * 64,
        attested_until=NOW + timedelta(hours=1),
        authority_scope_refs=scope,
    )
    return admit_agent_delegation(
        request=request,
        candidates=(candidate,),
        policy=AgentDelegationPolicy(),
        now=NOW,
    )


def test_work_plan_composes_into_existing_durable_agent_job() -> None:
    mastery = _mastery()
    plan = _plan()
    admission = _work_admission(plan, mastery)
    delegation = _delegation(plan)

    bundle = compose_work_control_plane(
        plan=plan,
        work_admission=admission,
        delegation=delegation,
        mastery_decisions=(mastery,),
        root_agent_id="jarvis-work-controller",
    )

    assignment = bundle.assignments[0]
    assert assignment.task_id == "legal-research"
    assert assignment.child_agent_id == SPECIALIST_ID
    assert assignment.mastery_decision_fingerprints == (mastery.fingerprint,)
    assert bundle.agent_job.objective_ref == plan.fingerprint
    assert bundle.agent_job.required_child_agent_ids == (SPECIALIST_ID,)
    assert bundle.business_execution_authority_granted is False
    assert bundle.agent_job.business_execution_authority_granted is False


def test_mastery_for_one_specialist_cannot_be_bound_to_another_worker() -> None:
    mastery = _mastery()
    plan = _plan()

    with pytest.raises(ValueError, match="work_bridge_specialist_worker_unavailable"):
        compose_work_control_plane(
            plan=plan,
            work_admission=_work_admission(plan, mastery),
            delegation=_delegation(plan, agent_id="legal-worker-other"),
            mastery_decisions=(mastery,),
            root_agent_id="jarvis-work-controller",
        )


def test_worker_without_exact_company_scope_cannot_receive_work() -> None:
    mastery = _mastery()
    plan = _plan()

    with pytest.raises(ValueError, match="work_bridge_company_scope_missing"):
        compose_work_control_plane(
            plan=plan,
            work_admission=_work_admission(plan, mastery),
            delegation=_delegation(plan, company_scope=False),
            mastery_decisions=(mastery,),
            root_agent_id="jarvis-work-controller",
        )


def test_admission_from_same_revision_but_other_plan_cannot_be_substituted() -> None:
    mastery = _mastery()
    original = _plan("Research legal position A")
    substituted = _plan("Research materially different legal position B")
    assert original.revision == substituted.revision
    assert original.fingerprint != substituted.fingerprint

    with pytest.raises(
        ValueError,
        match="work_bridge_admission_plan_fingerprint_mismatch",
    ):
        compose_work_control_plane(
            plan=substituted,
            work_admission=_work_admission(original, mastery),
            delegation=_delegation(substituted),
            mastery_decisions=(mastery,),
            root_agent_id="jarvis-work-controller",
        )
