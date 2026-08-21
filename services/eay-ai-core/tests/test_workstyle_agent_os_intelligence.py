from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.specialist_mastery_registry import (
    MasteryTier,
    SpecialistDomain,
    SpecialistScorecard,
    admit_specialist_mastery,
    build_specialist_evidence,
)
from app.workstyle_agent_os import (
    RPAExecutionMode,
    SpecialistRequirement,
    WorkActionClass,
    WorkArtifactRef,
    WorkCapability,
    WorkProgressEvent,
    WorkSessionState,
    WorkTaskDisposition,
    WorkTaskSpec,
    WorkTaskState,
    admit_work_plan,
    build_work_approval,
    build_work_plan,
    build_work_session,
    steer_work_session,
)

NOW = datetime(2026, 8, 21, 6, 50, tzinfo=UTC)


def _score(value: float = 0.995) -> SpecialistScorecard:
    return SpecialistScorecard(
        factuality=value,
        currentness=value,
        source_quality=value,
        citation_completeness=value,
        falsification_performance=value,
        calibration=value,
        tool_correctness=value,
        domain_benchmark=value,
        authority_adherence=value,
        adversarial_robustness=value,
    )


def _mastery(domain: SpecialistDomain, *, master: bool = True):
    specialist_id = f"specialist-{domain.value}"
    evidence = tuple(
        build_specialist_evidence(
            specialist_id=specialist_id,
            domain=domain,
            benchmark_id=f"{domain.value}-{index}",
            benchmark_version="v1",
            evaluated_cases=200,
            observed_at=NOW - timedelta(days=1),
            scorecard=_score(),
            evidence_refs=(f"evidence://{domain.value}/{index}",),
            synthetic=not master,
            production_shaped=master,
            independent_evaluator=master,
            reproducible=True,
        )
        for index in range(3)
    )
    decision = admit_specialist_mastery(
        specialist_id=specialist_id,
        domain=domain,
        evidence=evidence,
        now=NOW,
    )
    assert decision.admitted_tier is (
        MasteryTier.MASTER if master else MasteryTier.EXPERT
    )
    return decision


def _research_task() -> WorkTaskSpec:
    return WorkTaskSpec(
        task_id="research",
        objective="Establish current evidence and falsify competing explanations",
        required_capabilities=(
            WorkCapability.REASONING,
            WorkCapability.DEEP_RESEARCH,
            WorkCapability.CURRENT_WORLD,
        ),
        specialist_requirements=(
            SpecialistRequirement(
                domain=SpecialistDomain.DEEP_RESEARCH,
                minimum_tier=MasteryTier.EXPERT,
            ),
        ),
    )


def _rpa_task(*, dependency: str = "research") -> WorkTaskSpec:
    return WorkTaskSpec(
        task_id="rpa-change",
        objective="Apply the approved deterministic system change",
        required_capabilities=(WorkCapability.RPA, WorkCapability.REASONING),
        specialist_requirements=(
            SpecialistRequirement(
                domain=SpecialistDomain.RPA_AUTOMATION,
                minimum_tier=MasteryTier.MASTER,
            ),
        ),
        dependencies=(dependency,),
        action_class=WorkActionClass.EXTERNAL_MUTATION,
        rpa_mode=RPAExecutionMode.EXTERNAL_MUTATION,
    )


def _plan(*tasks: WorkTaskSpec, revision: int = 1):
    return build_work_plan(
        tenant_id="tenant-a",
        company_id="company-a",
        session_id="work-1",
        revision=revision,
        objective="Research the problem, prepare evidence, and act only if approved",
        tasks=tuple(tasks),
        created_at=NOW,
    )


def test_read_only_work_plan_binds_capability_and_specialist() -> None:
    plan = _plan(_research_task())
    admission = admit_work_plan(
        plan=plan,
        available_capabilities=(
            WorkCapability.REASONING,
            WorkCapability.DEEP_RESEARCH,
            WorkCapability.CURRENT_WORLD,
        ),
        mastery_decisions=(_mastery(SpecialistDomain.DEEP_RESEARCH),),
        approvals=(),
        now=NOW,
    )

    task = admission.task_admissions[0]
    assert task.disposition is WorkTaskDisposition.READY
    assert task.ready_for_governed_dispatch is True
    assert task.execution_authority_granted is False
    assert admission.execution_authority_granted is False


def test_missing_tool_capability_holds_work_instead_of_pretending() -> None:
    plan = _plan(_research_task())
    admission = admit_work_plan(
        plan=plan,
        available_capabilities=(WorkCapability.REASONING,),
        mastery_decisions=(_mastery(SpecialistDomain.DEEP_RESEARCH),),
        approvals=(),
        now=NOW,
    )

    assert admission.all_tasks_ready is False
    blockers = admission.task_admissions[0].blockers
    assert "work_capability_unavailable:deep_research" in blockers
    assert "work_capability_unavailable:current_world" in blockers


def test_master_required_task_rejects_merely_expert_specialist() -> None:
    plan = _plan(_research_task(), _rpa_task())
    admission = admit_work_plan(
        plan=plan,
        available_capabilities=(
            WorkCapability.REASONING,
            WorkCapability.DEEP_RESEARCH,
            WorkCapability.CURRENT_WORLD,
            WorkCapability.RPA,
        ),
        mastery_decisions=(
            _mastery(SpecialistDomain.DEEP_RESEARCH),
            _mastery(SpecialistDomain.RPA_AUTOMATION, master=False),
        ),
        approvals=(),
        now=NOW,
    )

    rpa = next(item for item in admission.task_admissions if item.task_id == "rpa-change")
    assert rpa.disposition is WorkTaskDisposition.HOLD
    assert (
        "work_specialist_tier_insufficient:rpa_automation:master"
        in rpa.blockers
    )


def test_external_rpa_mutation_requires_exact_scoped_approval() -> None:
    plan = _plan(_research_task(), _rpa_task())
    masteries = (
        _mastery(SpecialistDomain.DEEP_RESEARCH),
        _mastery(SpecialistDomain.RPA_AUTOMATION),
    )
    capabilities = (
        WorkCapability.REASONING,
        WorkCapability.DEEP_RESEARCH,
        WorkCapability.CURRENT_WORLD,
        WorkCapability.RPA,
    )

    held = admit_work_plan(
        plan=plan,
        available_capabilities=capabilities,
        mastery_decisions=masteries,
        approvals=(),
        now=NOW,
    )
    rpa_held = next(
        item for item in held.task_admissions if item.task_id == "rpa-change"
    )
    assert "work_consequential_action_approval_required" in rpa_held.blockers

    approval = build_work_approval(
        plan=plan,
        task_id="rpa-change",
        action_class=WorkActionClass.EXTERNAL_MUTATION,
        approved_by="user-a",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
    )
    admitted = admit_work_plan(
        plan=plan,
        available_capabilities=capabilities,
        mastery_decisions=masteries,
        approvals=(approval,),
        now=NOW,
    )
    rpa_ready = next(
        item for item in admitted.task_admissions if item.task_id == "rpa-change"
    )
    assert rpa_ready.disposition is WorkTaskDisposition.READY
    assert rpa_ready.approval_bound is True
    assert rpa_ready.ready_for_governed_dispatch is True
    assert rpa_ready.execution_authority_granted is False


def test_old_plan_approval_cannot_be_reused_after_replan() -> None:
    old_plan = _plan(_research_task(), _rpa_task(), revision=1)
    old_approval = build_work_approval(
        plan=old_plan,
        task_id="rpa-change",
        action_class=WorkActionClass.EXTERNAL_MUTATION,
        approved_by="user-a",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    new_plan = build_work_plan(
        tenant_id="tenant-a",
        company_id="company-a",
        session_id="work-1",
        revision=2,
        objective="Replanned objective",
        tasks=(_research_task(), _rpa_task()),
        created_at=NOW + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="work_approval_plan_revision_mismatch"):
        admit_work_plan(
            plan=new_plan,
            available_capabilities=(
                WorkCapability.REASONING,
                WorkCapability.DEEP_RESEARCH,
                WorkCapability.CURRENT_WORLD,
                WorkCapability.RPA,
            ),
            mastery_decisions=(
                _mastery(SpecialistDomain.DEEP_RESEARCH),
                _mastery(SpecialistDomain.RPA_AUTOMATION),
            ),
            approvals=(old_approval,),
            now=NOW + timedelta(minutes=2),
        )


def test_user_steering_invalidates_changed_task_and_dependants() -> None:
    research = _research_task()
    report = WorkTaskSpec(
        task_id="report",
        objective="Create the evidence report",
        required_capabilities=(WorkCapability.DOCUMENTS,),
        dependencies=("research",),
        action_class=WorkActionClass.ARTIFACT_WRITE,
        output_artifact_kinds=("document",),
    )
    independent = WorkTaskSpec(
        task_id="inventory",
        objective="Read the existing artifact inventory",
        required_capabilities=(WorkCapability.FILES,),
    )
    old_plan = _plan(research, report, independent)
    progress = WorkProgressEvent(
        event_id="event-inventory",
        task_id="inventory",
        state=WorkTaskState.SUCCEEDED,
        observed_at=NOW,
        summary="Inventory read complete",
    )
    artifact = WorkArtifactRef(
        artifact_id="artifact-inventory",
        artifact_kind="manifest",
        uri="artifact://inventory",
        content_sha256=hashlib.sha256(b"inventory").hexdigest(),
        producer_task_id="inventory",
        created_at=NOW,
    )
    session = build_work_session(
        plan=old_plan,
        updated_at=NOW,
        state=WorkSessionState.ACTIVE,
        artifacts=(artifact,),
        progress_events=(progress,),
    )

    changed_research = research.model_copy(
        update={"objective": "Research again with a newly supplied source"}
    )
    new_plan = build_work_plan(
        tenant_id="tenant-a",
        company_id="company-a",
        session_id="work-1",
        revision=2,
        objective=old_plan.objective,
        tasks=(changed_research, report, independent),
        created_at=NOW + timedelta(minutes=1),
    )
    steered = steer_work_session(
        session=session,
        new_plan=new_plan,
        issued_at=NOW + timedelta(minutes=2),
        issued_by="user-a",
        reason="Use the new source and re-evaluate dependent output",
    )

    receipt = steered.steering_receipts[-1]
    assert set(receipt.invalidated_task_ids) == {"research", "report"}
    assert tuple(item.task_id for item in steered.progress_events) == ("inventory",)
    assert tuple(item.artifact_id for item in steered.artifacts) == (
        "artifact-inventory",
    )
    assert steered.current_plan.revision == 2
    assert steered.state is WorkSessionState.PLANNING


def test_dependency_cycle_is_rejected() -> None:
    first = WorkTaskSpec(
        task_id="first",
        objective="First",
        required_capabilities=(WorkCapability.REASONING,),
        dependencies=("second",),
    )
    second = WorkTaskSpec(
        task_id="second",
        objective="Second",
        required_capabilities=(WorkCapability.REASONING,),
        dependencies=("first",),
    )

    with pytest.raises(ValueError, match="work_plan_dependency_cycle"):
        _plan(first, second)


def test_external_rpa_mode_cannot_hide_under_read_only_action_class() -> None:
    with pytest.raises(
        ValueError,
        match="work_external_rpa_requires_mutation_action_class",
    ):
        WorkTaskSpec(
            task_id="bad-rpa",
            objective="Mutate external system while pretending read-only",
            required_capabilities=(WorkCapability.RPA,),
            action_class=WorkActionClass.READ_ONLY,
            rpa_mode=RPAExecutionMode.EXTERNAL_MUTATION,
        )
