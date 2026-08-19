import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from app.engine_gateway import (
    EngineEndpoint,
    EngineGatewayError,
    EngineInvocationReceipt,
    EngineProvider,
    RegisteredEngine,
)
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceRoutingPlan,
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
    StrongReasoningRuntime,
    StrongReasoningStatus,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
EVIDENCE = "evidence://company-world/fulya"


def _registration(engine_id: str, family: str, score: float, model_id: str):
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id=engine_id,
            engine_class=EngineClass.LOCAL,
            modalities=(Modality.TEXT,),
            supports_long_horizon=True,
            supports_parallel_delegation=True,
            local_processing=True,
            maximum_privacy=PrivacyLevel.RESTRICTED,
            maximum_risk=TaskRisk.CRITICAL,
            exact_adapter_verified=True,
            production_enabled=True,
            benchmark_score=score,
            benchmark_evidence_ref=f"eval://{engine_id}",
            independent_provider_key=family,
        ),
        endpoint=EngineEndpoint(
            engine_id=engine_id,
            provider=EngineProvider.OLLAMA,
            model_id=model_id,
            base_url="http://127.0.0.1:11434",
        ),
    )


def _locals():
    return (
        _registration("local-qwen", "family:qwen", 0.90, "qwen-local"),
        _registration("local-mistral", "family:mistral", 0.85, "mistral-local"),
    )


def _task(**overrides):
    values = dict(
        task_id="reasoning://fulya-demand",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        external_processing_authorized=False,
    )
    values.update(overrides)
    return IntelligenceTask(**values)


def _context():
    return PaidTokenExecutionContext(
        subject_user_ref="user://erdi",
        tenant_ref="tenant://ys-tr",
        billing_cycle_ref="billing-cycle://2026-08",
        requested_at=NOW,
    )


def _info(selected=(), unresolved=()):
    return InformationGainPlan(
        gap_ids=tuple(unresolved),
        ranked=(),
        selected_investigation_ids=tuple(selected),
        total_selected_cost_units=0.0,
        unresolved_gap_ids=tuple(unresolved),
    )


def _plan(
    mode=ReasoningMode.LOCAL_COUNCIL,
    *,
    frontier=False,
    human=False,
    blockers=(),
):
    return ReasoningStrengthPlan(
        risk=ReasoningRisk.CRITICAL if human else ReasoningRisk.HIGH,
        mode=mode,
        unresolved_gap_count=0,
        calibrated_confidence_multiplier=1.0,
        local_council_required=mode in {ReasoningMode.LOCAL_COUNCIL, ReasoningMode.HUMAN_REVIEW},
        frontier_escalation_candidate=frontier,
        requires_platform_admin_paid_grant=frontier,
        human_review_required=human,
        blockers=tuple(blockers),
    )


def _payload(statement="Demand pressure is material", confidence=0.82, critiques=()):
    return json.dumps(
        {
            "claims": [
                {
                    "claim_key": "claim://demand-pressure",
                    "statement": statement,
                    "confidence": confidence,
                    "evidence_refs": [EVIDENCE],
                }
            ],
            "critiques": list(critiques),
            "proposed_action_refs": [],
        }
    )


class _NeverFrontier:
    def __init__(self):
        self.calls = 0

    async def invoke_primary(self, **kwargs):
        self.calls += 1
        raise AssertionError("frontier must not be called")


class _BlockedFrontier:
    def __init__(self):
        self.calls = 0

    async def invoke_primary(self, **kwargs):
        self.calls += 1
        raise EngineGatewayError("paid_token_invocation_not_authorized:paid_token_grant_missing")


class _AllowedFrontier:
    def __init__(self):
        self.calls = 0

    async def invoke_primary(self, **kwargs):
        self.calls += 1
        output = _payload(statement="Demand pressure is material", confidence=0.91)
        receipt = EngineInvocationReceipt(
            task_id=kwargs["task"].task_id,
            engine_id="frontier-gpt",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="frontier-model",
            output_text=output,
            input_tokens=50,
            output_tokens=25,
            provider_response_id="resp_test",
            external_processing=True,
            routing_plan=IntelligenceRoutingPlan(
                task_id=kwargs["task"].task_id,
                primary_engine_id="frontier-gpt",
                execution_permitted=True,
            ),
        )
        return SimpleNamespace(
            engine_receipt=receipt,
            paid_usage=SimpleNamespace(usage_ref="paid-token-usage:" + "a" * 64),
            local_free_execution=False,
        )


def test_investigate_first_makes_zero_model_calls():
    local_calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        local_calls.append(str(request.url))
        raise AssertionError("local model must not be called")

    frontier = _NeverFrontier()
    runtime = StrongReasoningRuntime(
        local_registrations=_locals(),
        frontier_runtime=frontier,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    plan = ReasoningStrengthPlan(
        risk=ReasoningRisk.CRITICAL,
        mode=ReasoningMode.INVESTIGATE_FIRST,
        unresolved_gap_count=1,
        calibrated_confidence_multiplier=1.0,
        local_council_required=False,
        frontier_escalation_candidate=False,
        requires_platform_admin_paid_grant=False,
        human_review_required=True,
        blockers=("reasoning_cannot_substitute_for_missing_live_company_truth",),
    )
    result = asyncio.run(
        runtime.execute(
            plan=plan,
            information_gain=_info(
                selected=("investigation://live-company-read",),
                unresolved=("decision:live_company_truth_receipt_missing",),
            ),
            task=_task(),
            prompt="Should Fulya change staffing?",
            claim_keys=("claim://demand-pressure",),
            allowed_evidence_refs=(EVIDENCE,),
            context=_context(),
        )
    )

    assert result.status is StrongReasoningStatus.NEEDS_INVESTIGATION
    assert result.engine_evidence == ()
    assert result.selected_investigation_ids == ("investigation://live-company-read",)
    assert local_calls == []
    assert frontier.calls == 0


def test_two_independent_local_model_families_form_council_without_paid_frontier():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["model"])
        text = _payload(confidence=0.86 if body["model"] == "qwen-local" else 0.80)
        return httpx.Response(
            200,
            json={"message": {"content": text}, "prompt_eval_count": 30, "eval_count": 20},
        )

    frontier = _NeverFrontier()
    runtime = StrongReasoningRuntime(
        local_registrations=_locals(),
        frontier_runtime=frontier,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    result = asyncio.run(
        runtime.execute(
            plan=_plan(),
            information_gain=_info(),
            task=_task(),
            prompt="Assess demand pressure from the supplied evidence.",
            claim_keys=("claim://demand-pressure",),
            allowed_evidence_refs=(EVIDENCE,),
            context=_context(),
        )
    )

    assert result.status is StrongReasoningStatus.COUNCIL_RESULT
    assert result.council is not None and result.council.decision_ready is True
    assert result.council.provider_diversity == 2
    assert {item.provider_key for item in result.engine_evidence} == {"family:qwen", "family:mistral"}
    assert all(item.private_chain_of_thought_retained is False for item in result.engine_evidence)
    assert result.paid_frontier_used is False
    assert frontier.calls == 0
    assert set(calls) == {"qwen-local", "mistral-local"}


def test_local_council_disagreement_stays_not_ready_without_frontier_authority():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["model"] == "qwen-local":
            text = _payload(confidence=0.84)
        else:
            text = json.dumps(
                {
                    "claims": [
                        {
                            "claim_key": "claim://other",
                            "statement": "Another claim",
                            "confidence": 0.75,
                            "evidence_refs": [EVIDENCE],
                        }
                    ],
                    "critiques": [
                        {
                            "target_claim_key": "claim://demand-pressure",
                            "stance": "refute",
                            "severity": "material",
                            "evidence_refs": [EVIDENCE],
                        }
                    ],
                    "proposed_action_refs": [],
                }
            )
        return httpx.Response(200, json={"message": {"content": text}})

    frontier = _NeverFrontier()
    runtime = StrongReasoningRuntime(
        local_registrations=_locals(),
        frontier_runtime=frontier,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    result = asyncio.run(
        runtime.execute(
            plan=_plan(frontier=False),
            information_gain=_info(),
            task=_task(),
            prompt="Assess the claim.",
            claim_keys=("claim://demand-pressure", "claim://other"),
            allowed_evidence_refs=(EVIDENCE,),
            context=_context(),
        )
    )

    assert result.council is not None
    assert result.council.decision_ready is False
    assert result.paid_frontier_used is False
    assert frontier.calls == 0
    assert result.execution_authority_granted is False


def test_council_insufficient_and_no_paid_grant_blocks_before_frontier_result():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        text = _payload() if body["model"] == "qwen-local" else "not-json"
        return httpx.Response(200, json={"message": {"content": text}})

    frontier = _BlockedFrontier()
    runtime = StrongReasoningRuntime(
        local_registrations=_locals(),
        frontier_runtime=frontier,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    result = asyncio.run(
        runtime.execute(
            plan=_plan(frontier=True),
            information_gain=_info(),
            task=_task(external_processing_authorized=True),
            prompt="Assess the claim.",
            claim_keys=("claim://demand-pressure",),
            allowed_evidence_refs=(EVIDENCE,),
            context=_context(),
        )
    )

    assert frontier.calls == 1
    assert result.status is StrongReasoningStatus.ESCALATION_BLOCKED
    assert result.paid_frontier_used is False
    assert any("paid_token_grant_missing" in blocker for blocker in result.blockers)


def test_governed_frontier_can_join_insufficient_local_council_but_never_grants_execution():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        text = _payload(confidence=0.82) if body["model"] == "qwen-local" else "not-json"
        return httpx.Response(200, json={"message": {"content": text}})

    frontier = _AllowedFrontier()
    runtime = StrongReasoningRuntime(
        local_registrations=_locals(),
        frontier_runtime=frontier,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    result = asyncio.run(
        runtime.execute(
            plan=_plan(frontier=True),
            information_gain=_info(),
            task=_task(external_processing_authorized=True),
            prompt="Assess the claim.",
            claim_keys=("claim://demand-pressure",),
            allowed_evidence_refs=(EVIDENCE,),
            context=_context(),
        )
    )

    assert frontier.calls == 1
    assert result.status is StrongReasoningStatus.ESCALATED_RESULT
    assert result.paid_frontier_used is True
    assert result.council is not None and result.council.decision_ready is True
    assert any(item.paid_usage_receipt_ref == "paid-token-usage:" + "a" * 64 for item in result.engine_evidence)
    assert result.paid_frontier_authority_granted is False
    assert result.execution_authority_granted is False


def test_critical_human_review_remains_required_even_when_local_council_agrees():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": _payload(confidence=0.9)}})

    frontier = _NeverFrontier()
    runtime = StrongReasoningRuntime(
        local_registrations=_locals(),
        frontier_runtime=frontier,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    result = asyncio.run(
        runtime.execute(
            plan=_plan(mode=ReasoningMode.HUMAN_REVIEW, frontier=True, human=True),
            information_gain=_info(),
            task=_task(risk=TaskRisk.CRITICAL),
            prompt="Assess critical decision.",
            claim_keys=("claim://demand-pressure",),
            allowed_evidence_refs=(EVIDENCE,),
            context=_context(),
        )
    )

    assert result.council is not None and result.council.decision_ready is True
    assert result.status is StrongReasoningStatus.HUMAN_REVIEW
    assert result.human_review_required is True
    assert frontier.calls == 0
