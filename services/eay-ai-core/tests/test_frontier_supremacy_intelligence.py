from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.frontier_supremacy_intelligence import (
    EngineDomainBenchmark,
    SoftwareEngineeringProof,
    SupremacyDomain,
    SupremacyRequest,
    admit_software_engineering_completion,
    execute_frontier_supremacy,
)
from app.intelligence_router import (
    IntelligenceRoutingPlan,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)

NOW = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)


@dataclass
class Receipt:
    engine_id: str
    output_text: str


class FakeGateway:
    def __init__(self, *, fail_first_verification: bool = False, critics: int = 2):
        self.fail_first_verification = fail_first_verification
        self.critics = critics
        self.calls: list[str] = []
        self.verification_round = 0

    def plan(self, task: IntelligenceTask) -> IntelligenceRoutingPlan:
        return IntelligenceRoutingPlan(
            task_id=task.task_id,
            primary_engine_id="sol",
            critic_engine_ids=("claude", "gemini")[: self.critics],
            council_required=True,
            execution_permitted=True,
        )

    async def invoke_primary(self, *, task: IntelligenceTask, prompt: str) -> Receipt:
        self.calls.append(prompt)
        if prompt.startswith("Repair the candidate"):
            return Receipt("sol", "Repaired evidence-bound answer")
        if "SYNTHESIZER" in prompt:
            return Receipt("sol", "Synthesized evidence-bound answer")
        return Receipt("sol", "Initial independent solution")

    async def invoke_routed_engines(
        self, *, task: IntelligenceTask, prompt: str
    ) -> tuple[Receipt, ...]:
        self.calls.append(prompt)
        if "FINAL VERIFIER" in prompt:
            self.verification_round += 1
            if self.fail_first_verification and self.verification_round == 1:
                critic_text = "VERDICT: FAIL\nA material objection remains."
                falsifier_text = "VERDICT: PASS\nNo other decisive issue."
            else:
                critic_text = "VERDICT: PASS\nReasoning checks out."
                falsifier_text = "VERDICT: PASS\nNo decisive counterexample remains."
        else:
            critic_text = "Independent critique"
            falsifier_text = "Independent falsification attempt"
        receipts = [Receipt("sol", "primary duplicate ignored")]
        if self.critics >= 1:
            receipts.append(Receipt("claude", critic_text))
        if self.critics >= 2:
            receipts.append(Receipt("gemini", falsifier_text))
        return tuple(receipts)


def task(**overrides) -> IntelligenceTask:
    values = dict(
        task_id="hard-problem",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        requires_long_horizon=False,
        requires_independent_critique=False,
    )
    values.update(overrides)
    return IntelligenceTask(**values)


def benchmarks(
    domain: SupremacyDomain,
    *,
    score: float = 1.0,
    sample_count: int = 200,
    independent: bool = True,
) -> tuple[EngineDomainBenchmark, ...]:
    return tuple(
        EngineDomainBenchmark(
            engine_id=engine_id,
            provider_key=provider_key,
            domain=domain,
            normalized_frontier_score=score,
            sample_count=sample_count,
            measured_at=NOW,
            evidence_ref=f"benchmark://{domain.value}/{engine_id}",
            independent_evaluator=independent,
        )
        for engine_id, provider_key in (
            ("sol", "openai"),
            ("claude", "anthropic"),
            ("gemini", "google"),
        )
    )


@pytest.mark.asyncio
async def test_three_provider_parity_council_solves_critiques_falsifies_and_verifies() -> None:
    gateway = FakeGateway()
    result = await execute_frontier_supremacy(
        gateway=gateway,
        request=SupremacyRequest(
            domain=SupremacyDomain.GENERAL_REASONING,
            task=task(),
            problem="Determine the strongest explanation and identify what would falsify it.",
            benchmarks=benchmarks(SupremacyDomain.GENERAL_REASONING),
        ),
    )
    assert result.decision_ready is True
    assert result.final_answer == "Synthesized evidence-bound answer"
    assert result.provider_diversity == 3
    assert result.selected_engine_ids == ("sol", "claude", "gemini")
    assert result.repair_rounds == 0
    assert result.execution_authority_granted is False
    assert result.superiority_claim_allowed is False
    assert any("independent SOLVER" in call for call in gateway.calls)
    assert any("adversarial reviewer" in call for call in gateway.calls)
    assert any("SYNTHESIZER" in call for call in gateway.calls)
    assert any("FINAL VERIFIER" in call for call in gateway.calls)


@pytest.mark.asyncio
async def test_failed_first_verification_triggers_one_bounded_repair_round() -> None:
    gateway = FakeGateway(fail_first_verification=True)
    result = await execute_frontier_supremacy(
        gateway=gateway,
        request=SupremacyRequest(
            domain=SupremacyDomain.NOVEL_PROBLEM_SOLVING,
            task=task(),
            problem="Solve a novel operational design problem with no known template.",
            benchmarks=benchmarks(SupremacyDomain.NOVEL_PROBLEM_SOLVING),
        ),
    )
    assert result.decision_ready is True
    assert result.final_answer == "Repaired evidence-bound answer"
    assert result.repair_rounds == 1


@pytest.mark.asyncio
async def test_two_engine_council_is_rejected_for_frontier_parity_mode() -> None:
    gateway = FakeGateway(critics=1)
    result = await execute_frontier_supremacy(
        gateway=gateway,
        request=SupremacyRequest(
            domain=SupremacyDomain.GENERAL_REASONING,
            task=task(),
            problem="Hard reasoning problem",
            benchmarks=benchmarks(SupremacyDomain.GENERAL_REASONING),
        ),
    )
    assert result.decision_ready is False
    assert "supremacy_three_engine_council_required" in result.blockers
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_099_domain_score_is_not_misrepresented_as_normalized_100_parity() -> None:
    gateway = FakeGateway()
    result = await execute_frontier_supremacy(
        gateway=gateway,
        request=SupremacyRequest(
            domain=SupremacyDomain.SOFTWARE_ENGINEERING,
            task=task(modalities=(Modality.TEXT, Modality.CODE)),
            problem="Produce a safe repository change",
            benchmarks=benchmarks(SupremacyDomain.SOFTWARE_ENGINEERING, score=0.99),
        ),
    )
    assert result.decision_ready is False
    assert any(code.startswith("supremacy_frontier_parity_not_met") for code in result.blockers)
    assert "supremacy_native_multimodal_execution_required" not in result.blockers
    assert gateway.calls == []


def test_deep_research_requires_grounding_packet_and_three_evidence_refs() -> None:
    with pytest.raises(ValueError, match="supremacy_grounded_domain_requires_context"):
        SupremacyRequest(
            domain=SupremacyDomain.DEEP_RESEARCH,
            task=task(),
            problem="Research a current market claim",
            benchmarks=benchmarks(SupremacyDomain.DEEP_RESEARCH),
        )
    with pytest.raises(ValueError, match="supremacy_grounded_domain_requires_three_evidence_refs"):
        SupremacyRequest(
            domain=SupremacyDomain.DEEP_RESEARCH,
            task=task(),
            problem="Research a current market claim",
            benchmarks=benchmarks(SupremacyDomain.DEEP_RESEARCH),
            grounding_context="Primary and secondary evidence packet",
            grounding_evidence_refs=("evidence://one", "evidence://two"),
        )


@pytest.mark.asyncio
async def test_generic_supremacy_cannot_fake_native_multimodal_execution_with_boolean() -> None:
    gateway = FakeGateway()
    request = SupremacyRequest(
        domain=SupremacyDomain.MULTIMODAL_WORLD,
        task=task(modalities=(Modality.TEXT, Modality.IMAGE)),
        problem="Understand the physical scene",
        benchmarks=benchmarks(SupremacyDomain.MULTIMODAL_WORLD),
        native_multimodal_gateway_verified=True,
    )
    result = await execute_frontier_supremacy(gateway=gateway, request=request)
    assert result.decision_ready is False
    assert "supremacy_native_multimodal_execution_required" in result.blockers
    assert gateway.calls == []


def test_software_engineering_completion_requires_exact_head_quality_proof() -> None:
    proof = SoftwareEngineeringProof(
        exact_head_sha="a" * 40,
        changed_files_reviewed=True,
        compile_passed=True,
        tests_passed=True,
        static_analysis_passed=True,
        security_regression_passed=True,
        exact_head_ci_passed=True,
        test_count=1234,
        evidence_refs=("ci://exact-head/123",),
    )
    accepted = admit_software_engineering_completion(proof)
    assert accepted.completion_ready is True
    assert accepted.blockers == ()
    rejected = admit_software_engineering_completion(
        proof.model_copy(update={"exact_head_ci_passed": False})
    )
    assert rejected.completion_ready is False
    assert rejected.blockers == ("exact_head_ci_not_green",)


@pytest.mark.asyncio
async def test_parity_evidence_requires_independent_evaluator_and_sample_depth() -> None:
    gateway = FakeGateway()
    result = await execute_frontier_supremacy(
        gateway=gateway,
        request=SupremacyRequest(
            domain=SupremacyDomain.GENERAL_REASONING,
            task=task(),
            problem="Hard reasoning problem",
            benchmarks=benchmarks(
                SupremacyDomain.GENERAL_REASONING,
                sample_count=20,
                independent=False,
            ),
        ),
    )
    assert result.decision_ready is False
    assert any(code.startswith("supremacy_benchmark_sample_count_insufficient") for code in result.blockers)
    assert any(code.startswith("supremacy_independent_evaluator_required") for code in result.blockers)
    assert gateway.calls == []
