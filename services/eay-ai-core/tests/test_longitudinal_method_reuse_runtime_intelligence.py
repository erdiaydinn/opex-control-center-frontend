from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.frontier3_certification_intelligence import FrontierCertificationDomain
from app.frontier_supremacy_intelligence import EngineDomainBenchmark, SupremacyDomain
from app.intelligence_router import (
    IntelligenceRoutingPlan,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.longitudinal_method_reliability_intelligence import (
    LongitudinalMethodReliabilityArtifact,
    MethodReliabilityState,
)
from app.longitudinal_method_reuse_runtime import (
    MethodReuseAdmission,
    MethodReuseAdmissionStatus,
    VerifiedMethodReuseRequest,
    VerifiedMethodReuseResult,
    build_method_reuse_admission,
    execute_verified_method_reuse_frontier,
)
from app.novel_problem_solver_intelligence import (
    NovelCandidateScore,
    NovelProblemDisposition,
    NovelProblemSolutionArtifact,
    VerifiedNovelFrontierRequest,
)
from app.transfer_generalization_intelligence import (
    TransferDisposition,
    TransferGeneralizationArtifact,
    TransferScenarioFamily,
    TransferScenarioScore,
)

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
TENANT = "tenant-a"
COMPANY = "company-a"
PROBLEM = "novel-problem-1"
METHOD = "solution-a"
REGIME = "regime-current"


def seal(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def sealed(model_type, **values):
    probe = model_type.model_construct(**values, fingerprint="0" * 64)
    payload = probe.model_dump(mode="json", exclude={"fingerprint"})
    return model_type.model_validate({**values, "fingerprint": seal(payload)})


def solution() -> NovelProblemSolutionArtifact:
    scores = (
        NovelCandidateScore(
            solution_id="solution-a",
            root_strategy_key="architecture-first",
            conservative_score=.91,
            evaluator_count=2,
            survived_falsifier_count=2,
            counterfactual_count=1,
            eligible=True,
        ),
        NovelCandidateScore(
            solution_id="solution-b",
            root_strategy_key="process-first",
            conservative_score=.79,
            evaluator_count=2,
            survived_falsifier_count=2,
            counterfactual_count=1,
            eligible=True,
        ),
        NovelCandidateScore(
            solution_id="solution-c",
            root_strategy_key="data-first",
            conservative_score=.72,
            evaluator_count=2,
            survived_falsifier_count=2,
            counterfactual_count=1,
            eligible=True,
        ),
    )
    return sealed(
        NovelProblemSolutionArtifact,
        problem_id=PROBLEM,
        tenant_id=TENANT,
        company_id=COMPANY,
        investigation_fingerprint="a" * 64,
        solution_ids=("solution-a", "solution-b", "solution-c"),
        root_strategy_keys=("architecture-first", "data-first", "process-first"),
        candidate_scores=scores,
        selected_solution_id=METHOD,
        decisive_margin=.12,
        disposition=NovelProblemDisposition.READY,
        blockers=(),
        evidence_refs=("solution://tree", "solution://review"),
    )


def transfer(
    source: NovelProblemSolutionArtifact,
    *,
    disposition: TransferDisposition = TransferDisposition.READY,
    source_fingerprint: str | None = None,
) -> TransferGeneralizationArtifact:
    ready = disposition is TransferDisposition.READY
    families = tuple(TransferScenarioFamily)
    scores = tuple(
        TransferScenarioScore(
            scenario_id=f"transfer-{item.value}",
            family=item,
            conservative_score=.88,
            independent_evaluator_count=2,
            eligible=ready,
            blockers=() if ready else ("transfer_hold",),
        )
        for item in families
    )
    return sealed(
        TransferGeneralizationArtifact,
        problem_id=PROBLEM,
        tenant_id=TENANT,
        company_id=COMPANY,
        source_solution_artifact_fingerprint=source_fingerprint or source.fingerprint,
        selected_solution_id=METHOD,
        tested_scope_families=families,
        scenario_count=len(scores),
        holdout_scenario_count=len(scores),
        ready_fraction=1.0 if ready else 0.0,
        worst_case_score=.88 if ready else 0.0,
        generalizable_invariants=("Preserve tenant isolation",),
        context_bound_assumptions=("Current regime remains represented",),
        scenario_scores=scores,
        disposition=disposition,
        blockers=() if ready else ("transfer_hold",),
        evidence_refs=("transfer://run", "transfer://review"),
        bounded_transfer_claim_allowed=ready,
    )


def reliability(
    source: TransferGeneralizationArtifact,
    *,
    state: MethodReliabilityState = MethodReliabilityState.TRUSTED,
    assessed_at: datetime | None = None,
    current_regime: str = REGIME,
    source_fingerprint: str | None = None,
) -> LongitudinalMethodReliabilityArtifact:
    trusted = state is MethodReliabilityState.TRUSTED
    return sealed(
        LongitudinalMethodReliabilityArtifact,
        problem_id=PROBLEM,
        tenant_id=TENANT,
        company_id=COMPANY,
        method_id=METHOD,
        source_transfer_artifact_fingerprint=source_fingerprint or source.fingerprint,
        current_regime_id=current_regime,
        assessment_as_of=assessed_at or (NOW - timedelta(hours=2)),
        episode_count=8,
        distinct_regime_count=2,
        current_regime_episode_count=5,
        current_negative_control_count=1,
        recovery_clean_episode_count=4,
        current_regime_worst_score=.86 if trusted else .61,
        episode_scores=(),
        state=state,
        blockers=() if trusted else ("current_regime_degradation",),
        evidence_refs=("outcome://current", "evaluation://current"),
        bounded_current_regime_reliability_claim_allowed=trusted,
    )


def frontier_task(*, fresh_certification: bool = True) -> IntelligenceTask:
    return IntelligenceTask(
        task_id="method-reuse-frontier",
        complexity=TaskComplexity.EXTREME,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_long_horizon=True,
        requires_independent_critique=True,
        certification_domain=(
            FrontierCertificationDomain.NOVEL_PROBLEM_SOLVING
            if fresh_certification
            else None
        ),
        requires_fresh_certification=fresh_certification,
    )


def benchmarks() -> tuple[EngineDomainBenchmark, ...]:
    return tuple(
        EngineDomainBenchmark(
            engine_id=engine_id,
            provider_key=provider,
            domain=SupremacyDomain.NOVEL_PROBLEM_SOLVING,
            normalized_frontier_score=1.0,
            sample_count=250,
            measured_at=NOW - timedelta(hours=1),
            evidence_ref=f"benchmark://reuse/{engine_id}",
            independent_evaluator=True,
        )
        for engine_id, provider in (
            ("sol", "openai"),
            ("claude", "anthropic"),
            ("gemini", "google"),
        )
    )


def request(
    *,
    state: MethodReliabilityState = MethodReliabilityState.TRUSTED,
    assessed_at: datetime | None = None,
    fresh_certification: bool = True,
    transfer_disposition: TransferDisposition = TransferDisposition.READY,
) -> VerifiedMethodReuseRequest:
    source = solution()
    transfer_artifact = transfer(source, disposition=transfer_disposition)
    reliability_artifact = reliability(
        transfer_artifact,
        state=state,
        assessed_at=assessed_at,
    )
    frontier = VerifiedNovelFrontierRequest(
        tenant_id=TENANT,
        company_id=COMPANY,
        problem="Reuse the already verified method only if current evidence still supports it",
        task=frontier_task(fresh_certification=fresh_certification),
        benchmarks=benchmarks(),
        solution_artifact=source,
    )
    return VerifiedMethodReuseRequest(
        tenant_id=TENANT,
        company_id=COMPANY,
        problem_id=PROBLEM,
        current_regime_id=REGIME,
        checked_at=NOW,
        frontier_request=frontier,
        transfer_artifact=transfer_artifact,
        reliability_artifact=reliability_artifact,
    )


@dataclass
class Receipt:
    engine_id: str
    output_text: str


class CountingGateway:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.provider_calls = 0

    def plan(self, task: IntelligenceTask) -> IntelligenceRoutingPlan:
        self.plan_calls += 1
        return IntelligenceRoutingPlan(
            task_id=task.task_id,
            primary_engine_id="sol",
            critic_engine_ids=("claude", "gemini"),
            council_required=True,
            execution_permitted=True,
            certification_admission_ref="capability-cert://fresh-reuse-council",
        )

    async def invoke_primary(self, *, task: IntelligenceTask, prompt: str) -> Receipt:
        self.provider_calls += 1
        if "SYNTHESIZER" in prompt:
            return Receipt("sol", "Reused method synthesis remains bounded by current evidence")
        return Receipt("sol", "Independent reused-method analysis")

    async def invoke_routed_engines(
        self, *, task: IntelligenceTask, prompt: str
    ) -> tuple[Receipt, ...]:
        self.provider_calls += 1
        if "FINAL VERIFIER" in prompt:
            return (
                Receipt("sol", "primary ignored"),
                Receipt("claude", "VERDICT: PASS\nCurrent-regime method evidence remains valid."),
                Receipt("gemini", "VERDICT: PASS\nNo material drift bypass was found."),
            )
        return (
            Receipt("sol", "primary ignored"),
            Receipt("claude", "Independent critique of method reuse"),
            Receipt("gemini", "Independent falsification of method reuse"),
        )


@pytest.mark.asyncio
async def test_trusted_fresh_exact_chain_enters_existing_frontier_runtime_without_minting_authority():
    gateway = CountingGateway()
    result = await execute_verified_method_reuse_frontier(
        gateway=gateway,
        request=request(),
    )

    assert result.admission.status is MethodReuseAdmissionStatus.ADMITTED
    assert result.frontier_deliberation_invoked is True
    assert result.frontier_result is not None
    assert result.frontier_result.supremacy.decision_ready is True
    assert gateway.plan_calls == 1
    assert gateway.provider_calls >= 4
    assert result.execution_authority_granted is False
    assert result.company_truth_promoted is False
    assert result.side_effect_authority_granted is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    (MethodReliabilityState.LIMITED, MethodReliabilityState.DISTRUSTED),
)
async def test_degraded_or_limited_method_is_held_before_gateway_or_provider_call(state):
    gateway = CountingGateway()
    result = await execute_verified_method_reuse_frontier(
        gateway=gateway,
        request=request(state=state),
    )

    assert result.admission.status is MethodReuseAdmissionStatus.HOLD
    assert any("current_regime_not_trusted" in item for item in result.admission.blockers)
    assert result.frontier_deliberation_invoked is False
    assert result.frontier_result is None
    assert gateway.plan_calls == 0
    assert gateway.provider_calls == 0


@pytest.mark.asyncio
async def test_stale_longitudinal_assessment_is_held_before_frontier_runtime():
    gateway = CountingGateway()
    result = await execute_verified_method_reuse_frontier(
        gateway=gateway,
        request=request(assessed_at=NOW - timedelta(hours=25)),
    )
    assert result.admission.status is MethodReuseAdmissionStatus.HOLD
    assert "method_reuse_reliability_assessment_stale" in result.admission.blockers
    assert gateway.plan_calls == 0
    assert gateway.provider_calls == 0


@pytest.mark.asyncio
async def test_missing_fresh_frontier_certification_is_held_before_gateway():
    gateway = CountingGateway()
    result = await execute_verified_method_reuse_frontier(
        gateway=gateway,
        request=request(fresh_certification=False),
    )
    assert result.admission.status is MethodReuseAdmissionStatus.HOLD
    assert "method_reuse_fresh_frontier_certification_required" in result.admission.blockers
    assert "method_reuse_novel_problem_certification_domain_required" in result.admission.blockers
    assert gateway.plan_calls == 0
    assert gateway.provider_calls == 0


@pytest.mark.asyncio
async def test_transfer_hold_cannot_be_overridden_by_trusted_historical_method_state():
    gateway = CountingGateway()
    result = await execute_verified_method_reuse_frontier(
        gateway=gateway,
        request=request(transfer_disposition=TransferDisposition.HOLD),
    )
    assert result.admission.status is MethodReuseAdmissionStatus.HOLD
    assert "method_reuse_transfer_not_ready" in result.admission.blockers
    assert "method_reuse_bounded_transfer_claim_missing" in result.admission.blockers
    assert gateway.plan_calls == 0


def test_exact_solution_transfer_reliability_chain_cannot_be_swapped_or_cross_regime():
    source = solution()
    wrong_transfer = transfer(source, source_fingerprint="b" * 64)
    good_transfer = transfer(source)
    good_reliability = reliability(good_transfer)
    frontier = VerifiedNovelFrontierRequest(
        tenant_id=TENANT,
        company_id=COMPANY,
        problem="Reuse an exact previously verified method under current evidence",
        task=frontier_task(),
        benchmarks=benchmarks(),
        solution_artifact=source,
    )

    with pytest.raises(ValidationError, match="transfer_solution_fingerprint_mismatch"):
        VerifiedMethodReuseRequest(
            tenant_id=TENANT,
            company_id=COMPANY,
            problem_id=PROBLEM,
            current_regime_id=REGIME,
            checked_at=NOW,
            frontier_request=frontier,
            transfer_artifact=wrong_transfer,
            reliability_artifact=good_reliability,
        )

    wrong_regime = reliability(good_transfer, current_regime="regime-old")
    with pytest.raises(ValidationError, match="current_regime_mismatch"):
        VerifiedMethodReuseRequest(
            tenant_id=TENANT,
            company_id=COMPANY,
            problem_id=PROBLEM,
            current_regime_id=REGIME,
            checked_at=NOW,
            frontier_request=frontier,
            transfer_artifact=good_transfer,
            reliability_artifact=wrong_regime,
        )

    wrong_source = reliability(good_transfer, source_fingerprint="c" * 64)
    with pytest.raises(ValidationError, match="reliability_transfer_fingerprint_mismatch"):
        VerifiedMethodReuseRequest(
            tenant_id=TENANT,
            company_id=COMPANY,
            problem_id=PROBLEM,
            current_regime_id=REGIME,
            checked_at=NOW,
            frontier_request=frontier,
            transfer_artifact=good_transfer,
            reliability_artifact=wrong_source,
        )


def test_future_reliability_and_tampering_are_rejected():
    source = solution()
    transfer_artifact = transfer(source)
    future = reliability(transfer_artifact, assessed_at=NOW + timedelta(minutes=1))
    frontier = VerifiedNovelFrontierRequest(
        tenant_id=TENANT,
        company_id=COMPANY,
        problem="Reject future or tampered method reliability evidence",
        task=frontier_task(),
        benchmarks=benchmarks(),
        solution_artifact=source,
    )
    with pytest.raises(ValidationError, match="future_reliability_assessment_forbidden"):
        VerifiedMethodReuseRequest(
            tenant_id=TENANT,
            company_id=COMPANY,
            problem_id=PROBLEM,
            current_regime_id=REGIME,
            checked_at=NOW,
            frontier_request=frontier,
            transfer_artifact=transfer_artifact,
            reliability_artifact=future,
        )

    admission = build_method_reuse_admission(request())
    tampered = admission.model_copy(update={"current_regime_id": "regime-tampered"})
    with pytest.raises(ValidationError, match="admission_fingerprint_mismatch"):
        MethodReuseAdmission.model_validate(tampered.model_dump(mode="json"))


def test_runtime_result_is_tamper_evident_and_never_authoritative():
    admission = build_method_reuse_admission(request())
    assert admission.status is MethodReuseAdmissionStatus.ADMITTED
    values = dict(
        tenant_id=TENANT,
        company_id=COMPANY,
        problem_id=PROBLEM,
        method_id=METHOD,
        admission=admission,
        frontier_deliberation_invoked=False,
        frontier_result=None,
    )
    probe = VerifiedMethodReuseResult.model_construct(**values, fingerprint="0" * 64)
    invalid = {**values, "fingerprint": seal(probe.model_dump(mode="json", exclude={"fingerprint"}))}
    with pytest.raises(ValidationError, match="frontier_invocation_must_match_admission"):
        VerifiedMethodReuseResult.model_validate(invalid)
