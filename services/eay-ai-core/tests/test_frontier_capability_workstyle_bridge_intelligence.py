from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.frontier3_certification_intelligence import (
    BenchmarkProtocolIdentity,
    BenchmarkScenarioCoverage,
    Frontier3CertificationPolicy,
    FrontierCertificationDomain,
    FrontierSystemMeasurement,
    JarvisDomainMeasurement,
    certify_frontier3_matrix,
)
from app.frontier_capability_gap_intelligence import (
    CapabilityGapWorkKind,
    CapabilityImprovementPlanState,
    build_capability_improvement_plan,
)
from app.frontier_capability_workstyle_bridge import (
    CapabilityWorkstyleDisposition,
    build_capability_gap_workstyle_bridge,
)
from app.workstyle_agent_os import WorkActionClass

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
DOMAIN = FrontierCertificationDomain.GENERAL_REASONING


def protocol(version: str = "v1") -> BenchmarkProtocolIdentity:
    return BenchmarkProtocolIdentity(
        protocol_id="frontier3-general-reasoning",
        protocol_version=version,
        task_set_id="taskset-general-reasoning",
        task_set_fingerprint="a" * 64,
        environment_fingerprint="b" * 64,
        metric_set_fingerprint="c" * 64,
    )


def coverage() -> BenchmarkScenarioCoverage:
    return BenchmarkScenarioCoverage(
        holdout=True,
        out_of_distribution=True,
        adversarial=True,
        temporal=True,
    )


def jarvis(*, score: float, lower: float, upper: float, safety: bool = False):
    return JarvisDomainMeasurement(
        measurement_id=f"jarvis-{score}-{int(safety)}",
        domain=DOMAIN,
        system_version="jarvis-v-next",
        normalized_score=score,
        confidence_lower=lower,
        confidence_upper=upper,
        confidence_level=0.95,
        sample_count=240,
        measured_at=NOW - timedelta(days=1),
        protocol=protocol(),
        scenario_coverage=coverage(),
        independent_evaluator_ref="eval-jarvis",
        evidence_refs=("benchmark://jarvis/run", "benchmark://jarvis/review"),
        critical_safety_regression=safety,
    )


def peers(*, protocol_versions=("v1", "v1", "v1")):
    rows = (
        ("frontier-a", "provider-a", 0.91, 0.89, 0.93),
        ("frontier-b", "provider-b", 0.93, 0.91, 0.95),
        ("frontier-c", "provider-c", 0.95, 0.93, 0.97),
    )
    return tuple(
        FrontierSystemMeasurement(
            measurement_id=f"peer-{index}-{version}",
            domain=DOMAIN,
            system_id=system,
            system_version=f"{system}-2026-08",
            provider_family=provider,
            normalized_score=score,
            confidence_lower=lower,
            confidence_upper=upper,
            confidence_level=0.95,
            sample_count=240,
            measured_at=NOW - timedelta(days=1),
            protocol=protocol(version),
            scenario_coverage=coverage(),
            independent_evaluator_ref=f"eval-peer-{index}",
            frontier_qualification_evidence_ref=f"frontier://qualification/{system}",
            evidence_refs=(f"benchmark://{system}/run", f"benchmark://{system}/review"),
            frontier_qualified=True,
        )
        for index, ((system, provider, score, lower, upper), version) in enumerate(
            zip(rows, protocol_versions, strict=True), start=1
        )
    )


def certification(*, measurement, peer_measurements=None):
    return certify_frontier3_matrix(
        certification_id=f"cert-{measurement.measurement_id}",
        tenant_id="tenant-a",
        company_id="company-a",
        jarvis_system_id="jarvis",
        jarvis_system_version="jarvis-v-next",
        assessed_at=NOW,
        jarvis_measurements=(measurement,),
        frontier_measurements=peer_measurements or peers(),
        policy=Frontier3CertificationPolicy(required_domains=(DOMAIN,)),
    )


def open_plan():
    return build_capability_improvement_plan(
        source=certification(measurement=jarvis(score=0.90, lower=0.88, upper=0.92)),
        tenant_id="tenant-a",
        company_id="company-a",
    )


def complete_plan():
    return build_capability_improvement_plan(
        source=certification(measurement=jarvis(score=0.96, lower=0.94, upper=0.98)),
        tenant_id="tenant-a",
        company_id="company-a",
    )


def multi_blocker_plan():
    source = certification(
        measurement=jarvis(score=0.90, lower=0.88, upper=0.92, safety=True),
        peer_measurements=peers(protocol_versions=("v1", "v2", "v1")),
    )
    return build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )


def test_open_gap_plan_becomes_exact_workstyle_task_graph():
    source = open_plan()
    assert source.state is CapabilityImprovementPlanState.OPEN
    bridge = build_capability_gap_workstyle_bridge(
        plan=source,
        session_id="frontier-gap-session",
        created_at=NOW,
    )
    assert bridge.disposition is CapabilityWorkstyleDisposition.PLANNED
    assert bridge.work_plan is not None
    assert bridge.work_plan.tenant_id == source.tenant_id
    assert bridge.work_plan.company_id == source.company_id
    assert len(bridge.work_plan.tasks) == len(source.work_items)
    assert tuple(item.work_item_id for item in bridge.task_bindings) == tuple(
        item.work_item_id
        for item in sorted(
            source.work_items,
            key=lambda item: (-item.priority, item.domain.value, item.kind.value, item.work_item_id),
        )
    )
    assert all(
        task.action_class is WorkActionClass.ARTIFACT_WRITE
        for task in bridge.work_plan.tasks
    )


def test_same_domain_high_priority_remediation_precedes_lower_priority_work():
    source = multi_blocker_plan()
    kinds = {item.kind for item in source.work_items}
    assert CapabilityGapWorkKind.SAFETY_REMEDIATION in kinds
    assert CapabilityGapWorkKind.PROTOCOL_REPAIR in kinds
    bridge = build_capability_gap_workstyle_bridge(
        plan=source,
        session_id="multi-blocker-session",
        created_at=NOW,
    )
    assert bridge.work_plan is not None
    tasks = bridge.work_plan.tasks
    assert len(tasks) >= 2
    assert bridge.task_bindings[0].priority >= bridge.task_bindings[1].priority
    assert tasks[0].dependencies == ()
    for previous, current in zip(tasks, tasks[1:]):
        assert current.dependencies == (previous.task_id,)


def test_bridge_never_converts_gap_work_into_mutation_or_self_improvement_authority():
    bridge = build_capability_gap_workstyle_bridge(
        plan=open_plan(),
        session_id="authority-session",
        created_at=NOW,
    )
    assert bridge.work_plan is not None
    assert all(
        task.action_class not in {WorkActionClass.EXTERNAL_MUTATION, WorkActionClass.HIGH_IMPACT}
        for task in bridge.work_plan.tasks
    )
    assert not bridge.execution_authority_granted
    assert not bridge.automatic_training_allowed
    assert not bridge.automatic_code_change_allowed
    assert not bridge.automatic_provider_change_allowed
    assert not bridge.automatic_policy_update_allowed
    assert not bridge.company_truth_promoted
    assert not bridge.work_plan.execution_authority_granted


def test_bridge_is_deterministic_for_same_evidence_session_and_time():
    source = open_plan()
    first = build_capability_gap_workstyle_bridge(
        plan=source,
        session_id="deterministic-session",
        created_at=NOW,
    )
    second = build_capability_gap_workstyle_bridge(
        plan=source,
        session_id="deterministic-session",
        created_at=NOW,
    )
    assert first.fingerprint == second.fingerprint
    assert first.work_plan is not None and second.work_plan is not None
    assert first.work_plan.fingerprint == second.work_plan.fingerprint
    assert first.task_bindings == second.task_bindings


def test_complete_frontier_plan_creates_no_fake_work():
    source = complete_plan()
    assert source.state is CapabilityImprovementPlanState.COMPLETE
    bridge = build_capability_gap_workstyle_bridge(
        plan=source,
        session_id="complete-session",
        created_at=NOW,
    )
    assert bridge.disposition is CapabilityWorkstyleDisposition.NO_WORK
    assert bridge.work_plan is None
    assert bridge.task_bindings == ()


def test_tampered_source_plan_is_revalidated_before_work_generation():
    source = open_plan().model_copy(update={"fingerprint": "0" * 64})
    with pytest.raises(ValidationError, match="capability_gap_plan_fingerprint_mismatch"):
        build_capability_gap_workstyle_bridge(
            plan=source,
            session_id="tampered-session",
            created_at=NOW,
        )


def test_bridge_requires_timezone_aware_work_plan_time():
    with pytest.raises(ValueError, match="created_at_requires_timezone"):
        build_capability_gap_workstyle_bridge(
            plan=open_plan(),
            session_id="naive-time-session",
            created_at=datetime(2026, 8, 23),
        )
