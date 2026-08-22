from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
    CapabilityGapClosureArtifact,
    CapabilityGapClosureState,
    CapabilityGapWorkKind,
    CapabilityImprovementPlan,
    CapabilityImprovementPlanState,
    CapabilityImprovementTarget,
    build_capability_improvement_plan,
    verify_capability_gap_closure,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
DOMAIN = FrontierCertificationDomain.GENERAL_REASONING
VERSION = "jarvis-v-next"


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


def jarvis(
    *,
    score: float,
    lower: float,
    upper: float,
    safety_regression: bool = False,
    measured_at: datetime | None = None,
) -> JarvisDomainMeasurement:
    return JarvisDomainMeasurement(
        measurement_id=f"jarvis-{score}-{lower}-{upper}-{int(safety_regression)}",
        domain=DOMAIN,
        system_version=VERSION,
        normalized_score=score,
        confidence_lower=lower,
        confidence_upper=upper,
        confidence_level=0.95,
        sample_count=240,
        measured_at=measured_at or NOW - timedelta(days=1),
        protocol=protocol(),
        scenario_coverage=coverage(),
        independent_evaluator_ref="eval-jarvis",
        evidence_refs=("benchmark://jarvis/run", "benchmark://jarvis/review"),
        critical_safety_regression=safety_regression,
    )


def peers(
    *,
    measured_at: datetime | None = None,
    protocol_versions: tuple[str, str, str] = ("v1", "v1", "v1"),
) -> tuple[FrontierSystemMeasurement, ...]:
    values = (
        ("frontier-a", "provider-a", 0.91, 0.89, 0.93),
        ("frontier-b", "provider-b", 0.93, 0.91, 0.95),
        ("frontier-c", "provider-c", 0.95, 0.93, 0.97),
    )
    return tuple(
        FrontierSystemMeasurement(
            measurement_id=f"peer-{idx}-{protocol_version}-{(measured_at or NOW).date()}",
            domain=DOMAIN,
            system_id=system,
            system_version=f"{system}-2026-08",
            provider_family=provider,
            normalized_score=score,
            confidence_lower=lower,
            confidence_upper=upper,
            confidence_level=0.95,
            sample_count=240,
            measured_at=measured_at or NOW - timedelta(days=1),
            protocol=protocol(protocol_version),
            scenario_coverage=coverage(),
            independent_evaluator_ref=f"eval-peer-{idx}",
            frontier_qualification_evidence_ref=f"frontier://qualification/{system}",
            evidence_refs=(
                f"benchmark://{system}/run",
                f"benchmark://{system}/review",
            ),
            frontier_qualified=True,
        )
        for idx, ((system, provider, score, lower, upper), protocol_version) in enumerate(
            zip(values, protocol_versions, strict=True),
            start=1,
        )
    )


def certification(
    *,
    jarvis_measurement: JarvisDomainMeasurement,
    peer_measurements: tuple[FrontierSystemMeasurement, ...] | None = None,
    assessed_at: datetime = NOW,
    tenant_id: str = "tenant-a",
    company_id: str = "company-a",
):
    return certify_frontier3_matrix(
        certification_id=f"cert-{assessed_at.timestamp()}-{jarvis_measurement.normalized_score}",
        tenant_id=tenant_id,
        company_id=company_id,
        jarvis_system_id="jarvis",
        jarvis_system_version=VERSION,
        assessed_at=assessed_at,
        jarvis_measurements=(jarvis_measurement,),
        frontier_measurements=peer_measurements or peers(),
        policy=Frontier3CertificationPolicy(required_domains=(DOMAIN,)),
    )


def below_source():
    return certification(jarvis_measurement=jarvis(score=0.90, lower=0.88, upper=0.92))


def parity_source(*, assessed_at: datetime = NOW):
    measured_at = assessed_at - timedelta(days=1)
    return certification(
        jarvis_measurement=jarvis(
            score=0.96,
            lower=0.94,
            upper=0.98,
            measured_at=measured_at,
        ),
        peer_measurements=peers(measured_at=measured_at),
        assessed_at=assessed_at,
    )


def superior_source(*, assessed_at: datetime):
    measured_at = assessed_at - timedelta(days=1)
    return certification(
        jarvis_measurement=jarvis(
            score=0.995,
            lower=0.985,
            upper=1.0,
            measured_at=measured_at,
        ),
        peer_measurements=peers(measured_at=measured_at),
        assessed_at=assessed_at,
    )


def test_below_frontier_becomes_measurable_capability_improvement_work() -> None:
    source = below_source()
    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert plan.state is CapabilityImprovementPlanState.OPEN
    assert plan.open_domains == (DOMAIN,)
    item = next(item for item in plan.work_items if item.kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    assert item.raw_score_gap == pytest.approx(0.05)
    assert item.priority > 76
    assert any("strongest eligible frontier score" in rule for rule in item.acceptance_criteria)
    assert item.execution_authority_granted is False
    assert item.automatic_training_allowed is False
    assert plan.claim_upgrade_allowed is False


def test_safety_protocol_and_staleness_generate_the_right_work_instead_of_blind_training() -> None:
    unsafe_source = certification(
        jarvis_measurement=jarvis(
            score=0.96,
            lower=0.94,
            upper=0.98,
            safety_regression=True,
        )
    )
    unsafe_plan = build_capability_improvement_plan(
        source=unsafe_source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert unsafe_plan.work_items[0].kind is CapabilityGapWorkKind.SAFETY_REMEDIATION
    assert unsafe_plan.work_items[0].priority == 100

    protocol_source = certification(
        jarvis_measurement=jarvis(score=0.96, lower=0.94, upper=0.98),
        peer_measurements=peers(protocol_versions=("v1", "v2", "v1")),
    )
    protocol_plan = build_capability_improvement_plan(
        source=protocol_source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert any(item.kind is CapabilityGapWorkKind.PROTOCOL_REPAIR for item in protocol_plan.work_items)

    stale_time = NOW - timedelta(days=31)
    stale_source = certification(
        jarvis_measurement=jarvis(score=0.96, lower=0.94, upper=0.98),
        peer_measurements=peers(measured_at=stale_time),
    )
    stale_plan = build_capability_improvement_plan(
        source=stale_source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert any(item.kind is CapabilityGapWorkKind.BENCHMARK_REFRESH for item in stale_plan.work_items)


def test_parity_target_is_complete_once_domain_is_certified() -> None:
    plan = build_capability_improvement_plan(
        source=parity_source(),
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert plan.state is CapabilityImprovementPlanState.COMPLETE
    assert plan.open_domains == ()
    assert plan.target_satisfied_domains == (DOMAIN,)
    assert plan.work_items == ()
    assert plan.claim_upgrade_allowed is False


def test_superiority_target_does_not_mislabel_parity_as_complete() -> None:
    plan = build_capability_improvement_plan(
        source=parity_source(),
        tenant_id="tenant-a",
        company_id="company-a",
        target=CapabilityImprovementTarget.MEASURED_SUPERIORITY,
    )
    assert plan.state is CapabilityImprovementPlanState.OPEN
    assert plan.open_domains == (DOMAIN,)
    assert len(plan.work_items) == 1
    assert plan.work_items[0].kind is CapabilityGapWorkKind.UNCERTAINTY_REDUCTION


def test_gap_closure_requires_a_newer_sealed_certification_that_reaches_target() -> None:
    source = below_source()
    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    work_item = next(item for item in plan.work_items if item.kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    candidate = parity_source(assessed_at=NOW + timedelta(days=1))
    closure = verify_capability_gap_closure(
        plan=plan,
        work_item_id=work_item.work_item_id,
        candidate=candidate,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert closure.state is CapabilityGapClosureState.CLOSED
    assert closure.bounded_gap_closure_claim_allowed is True
    assert closure.matrix_claim_upgrade_allowed is False
    assert closure.execution_authority_granted is False
    assert closure.automatic_model_weight_update_allowed is False


def test_newer_candidate_that_still_misses_target_does_not_close_gap() -> None:
    source = below_source()
    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    item = next(item for item in plan.work_items if item.kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    assessed = NOW + timedelta(days=1)
    candidate = certification(
        jarvis_measurement=jarvis(
            score=0.91,
            lower=0.89,
            upper=0.93,
            measured_at=assessed - timedelta(days=1),
        ),
        peer_measurements=peers(measured_at=assessed - timedelta(days=1)),
        assessed_at=assessed,
    )
    closure = verify_capability_gap_closure(
        plan=plan,
        work_item_id=item.work_item_id,
        candidate=candidate,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert closure.state is CapabilityGapClosureState.NOT_CLOSED
    assert closure.bounded_gap_closure_claim_allowed is False
    assert closure.blockers == ("capability_gap_closure_target_not_met",)


def test_superiority_gap_closes_only_with_statistical_superiority() -> None:
    source = parity_source()
    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
        target=CapabilityImprovementTarget.MEASURED_SUPERIORITY,
    )
    item = plan.work_items[0]
    parity_candidate = parity_source(assessed_at=NOW + timedelta(days=1))
    not_closed = verify_capability_gap_closure(
        plan=plan,
        work_item_id=item.work_item_id,
        candidate=parity_candidate,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert not_closed.state is CapabilityGapClosureState.NOT_CLOSED

    superior_candidate = superior_source(assessed_at=NOW + timedelta(days=2))
    closed = verify_capability_gap_closure(
        plan=plan,
        work_item_id=item.work_item_id,
        candidate=superior_candidate,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    assert closed.state is CapabilityGapClosureState.CLOSED


def test_same_or_older_certification_cannot_be_replayed_as_gap_closure() -> None:
    source = below_source()
    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    item = next(item for item in plan.work_items if item.kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    with pytest.raises(ValueError, match="capability_gap_closure_requires_new_certification"):
        verify_capability_gap_closure(
            plan=plan,
            work_item_id=item.work_item_id,
            candidate=source,
            tenant_id="tenant-a",
            company_id="company-a",
        )

    changed_same_time = certification(
        jarvis_measurement=jarvis(score=0.91, lower=0.89, upper=0.93),
        assessed_at=NOW,
    )
    with pytest.raises(ValueError, match="capability_gap_closure_candidate_must_be_newer"):
        verify_capability_gap_closure(
            plan=plan,
            work_item_id=item.work_item_id,
            candidate=changed_same_time,
            tenant_id="tenant-a",
            company_id="company-a",
        )


def test_plan_and_closure_are_exact_tenant_company_bound() -> None:
    source = below_source()
    with pytest.raises(ValueError, match="capability_gap_cross_tenant_source_forbidden"):
        build_capability_improvement_plan(
            source=source,
            tenant_id="tenant-b",
            company_id="company-a",
        )
    with pytest.raises(ValueError, match="capability_gap_cross_company_source_forbidden"):
        build_capability_improvement_plan(
            source=source,
            tenant_id="tenant-a",
            company_id="company-b",
        )

    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    item = next(item for item in plan.work_items if item.kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    candidate = parity_source(assessed_at=NOW + timedelta(days=1))
    with pytest.raises(ValueError, match="capability_gap_closure_cross_tenant_forbidden"):
        verify_capability_gap_closure(
            plan=plan,
            work_item_id=item.work_item_id,
            candidate=candidate,
            tenant_id="tenant-b",
            company_id="company-a",
        )


def test_plan_and_closure_tampering_or_authority_escalation_is_rejected() -> None:
    source = below_source()
    plan = build_capability_improvement_plan(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
    )
    tampered = plan.model_copy(update={"open_domains": ()})
    with pytest.raises(ValueError):
        CapabilityImprovementPlan.model_validate(tampered.model_dump(mode="json"))

    escalated = plan.model_copy(update={"automatic_training_allowed": True})
    with pytest.raises(ValueError, match="capability_gap_plan_never_mints_change_or_claim_authority"):
        CapabilityImprovementPlan.model_validate(escalated.model_dump(mode="json"))

    item = next(item for item in plan.work_items if item.kind is CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT)
    closure = verify_capability_gap_closure(
        plan=plan,
        work_item_id=item.work_item_id,
        candidate=parity_source(assessed_at=NOW + timedelta(days=1)),
        tenant_id="tenant-a",
        company_id="company-a",
    )
    escalated_closure = closure.model_copy(update={"matrix_claim_upgrade_allowed": True})
    with pytest.raises(
        ValueError,
        match="capability_gap_closure_never_mints_change_or_matrix_claim_authority",
    ):
        CapabilityGapClosureArtifact.model_validate(escalated_closure.model_dump(mode="json"))
