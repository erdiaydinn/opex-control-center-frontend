import asyncio
import json

import httpx

from app.engine_gateway import (
    EngineEndpoint,
    EngineGateway,
    EngineProvider,
    RegisteredEngine,
)
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.mission_execution import (
    AuthorizationDecision,
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
    execute_mission_until_blocked,
)
from app.mission_runtime import (
    MissionDefinition,
    MissionStatus,
    MissionStep,
    new_checkpoint,
)


def _gateway():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "eay-ops:0.1"
        return httpx.Response(
            200,
            json={
                "message": {"content": "SKU and quantity are internally consistent."},
                "prompt_eval_count": 18,
                "eval_count": 8,
            },
        )

    profile = IntelligenceEngine(
        engine_id="ollama-local",
        engine_class=EngineClass.LOCAL,
        modalities=(Modality.TEXT,),
        supports_tools=False,
        supports_long_horizon=False,
        supports_parallel_delegation=False,
        local_processing=True,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=0.90,
        benchmark_evidence_ref="benchmark://" + "a" * 64,
        independent_provider_key="ollama-local",
    )
    registration = RegisteredEngine(
        profile=profile,
        endpoint=EngineEndpoint(
            engine_id="ollama-local",
            provider=EngineProvider.OLLAMA,
            model_id="eay-ops:0.1",
            base_url="http://127.0.0.1:11434",
        ),
    )
    return EngineGateway(
        [registration],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )


def _task():
    return IntelligenceTask(
        task_id="validate-stock-adjustment",
        complexity=TaskComplexity.STANDARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
    )


def _mission():
    return MissionDefinition(
        mission_id="synthetic-fulya-stock-adjustment",
        objective="Validate and adjust synthetic Fulya stock with authoritative read-back",
        tenant_id="YS_TR",
        steps=(
            MissionStep(
                step_id="reason",
                description="Validate target, quantity and reason before action",
            ),
            MissionStep(
                step_id="adjust",
                description="Apply synthetic inventory adjustment",
                depends_on=("reason",),
                side_effect=True,
                required_permission="inventory.adjust",
                idempotency_key="synthetic:fulya:8690000000001:zayi:-3",
                effect_verifier_ref="synthetic://inventory/read-back",
            ),
        ),
    )


def _specs():
    return (
        MissionExecutionSpec(
            step_id="reason",
            kind=MissionExecutionKind.REASONING,
            intelligence_task=_task(),
            prompt="Validate Fulya barcode 8690000000001, quantity -3, reason ZAYI.",
        ),
        MissionExecutionSpec(
            step_id="adjust",
            kind=MissionExecutionKind.CAPABILITY,
            capability_ref="synthetic.inventory.adjust",
        ),
    )


def test_end_to_end_reason_action_verify_checkpoint_and_resume_is_idempotent():
    inventory = {("Fulya", "8690000000001"): 10}
    applied = set()
    action_calls = 0

    async def authorize(definition, step, capability_ref):
        assert step.required_permission == "inventory.adjust"
        assert capability_ref == "synthetic.inventory.adjust"
        return AuthorizationDecision(
            allowed=True,
            evidence_ref="authz://YS_TR/erdi/inventory.adjust",
        )

    async def adjust(definition, step, state, idempotency_key):
        nonlocal action_calls
        action_calls += 1
        key = ("Fulya", "8690000000001")
        before = inventory[key]
        if idempotency_key not in applied:
            inventory[key] -= 3
            applied.add(idempotency_key)
        after = inventory[key]
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=(before == 10 and after == 7),
            evidence_refs=("synthetic://inventory/before/10", "synthetic://inventory/after/7"),
            transaction_ref="synthetic-tx://adjustment-1",
        )

    summary = asyncio.run(
        execute_mission_until_blocked(
            definition=_mission(),
            checkpoint=new_checkpoint(_mission()),
            specs=_specs(),
            gateway=_gateway(),
            reasoning_evidence_writer=lambda receipt: f"engine-output://{receipt.engine_id}/{receipt.task_id}",
            capability_handlers={"synthetic.inventory.adjust": adjust},
            authorization_checker=authorize,
        )
    )

    assert summary.checkpoint.status is MissionStatus.COMPLETED
    assert summary.transitions_executed == 2
    assert summary.reasoning_engine_ids == ("ollama-local",)
    assert inventory[("Fulya", "8690000000001")] == 7
    assert action_calls == 1
    adjust_state = {item.step_id: item for item in summary.checkpoint.steps}["adjust"]
    assert "authz://YS_TR/erdi/inventory.adjust" in adjust_state.evidence_refs
    assert "synthetic://inventory/after/7" in adjust_state.evidence_refs
    assert "synthetic-tx://adjustment-1" in adjust_state.evidence_refs

    resumed = asyncio.run(
        execute_mission_until_blocked(
            definition=_mission(),
            checkpoint=summary.checkpoint,
            specs=_specs(),
            gateway=_gateway(),
            reasoning_evidence_writer=lambda receipt: f"engine-output://{receipt.engine_id}/{receipt.task_id}",
            capability_handlers={"synthetic.inventory.adjust": adjust},
            authorization_checker=authorize,
        )
    )

    assert resumed.transitions_executed == 0
    assert resumed.checkpoint.status is MissionStatus.COMPLETED
    assert inventory[("Fulya", "8690000000001")] == 7
    assert action_calls == 1


def test_unknown_write_outcome_halts_and_is_not_blindly_replayed_on_resume():
    inventory = {("Fulya", "8690000000001"): 10}
    action_calls = 0

    async def authorize(definition, step, capability_ref):
        return AuthorizationDecision(
            allowed=True,
            evidence_ref="authz://YS_TR/erdi/inventory.adjust",
        )

    async def ambiguous_adjust(definition, step, state, idempotency_key):
        nonlocal action_calls
        action_calls += 1
        inventory[("Fulya", "8690000000001")] -= 3
        return CapabilityExecutionOutcome(
            succeeded=False,
            ambiguous_outcome=True,
            evidence_refs=("synthetic://request/dispatched",),
            error_code="network_timeout_after_submit",
        )

    first = asyncio.run(
        execute_mission_until_blocked(
            definition=_mission(),
            checkpoint=new_checkpoint(_mission()),
            specs=_specs(),
            gateway=_gateway(),
            reasoning_evidence_writer=lambda receipt: f"engine-output://{receipt.engine_id}/{receipt.task_id}",
            capability_handlers={"synthetic.inventory.adjust": ambiguous_adjust},
            authorization_checker=authorize,
        )
    )

    assert first.checkpoint.status is MissionStatus.HALTED
    assert inventory[("Fulya", "8690000000001")] == 7
    assert action_calls == 1
    assert "capability_outcome_ambiguous:synthetic.inventory.adjust" in first.blockers

    resumed = asyncio.run(
        execute_mission_until_blocked(
            definition=_mission(),
            checkpoint=first.checkpoint,
            specs=_specs(),
            gateway=_gateway(),
            reasoning_evidence_writer=lambda receipt: f"engine-output://{receipt.engine_id}/{receipt.task_id}",
            capability_handlers={"synthetic.inventory.adjust": ambiguous_adjust},
            authorization_checker=authorize,
        )
    )

    assert resumed.transitions_executed == 0
    assert resumed.checkpoint.status is MissionStatus.HALTED
    assert inventory[("Fulya", "8690000000001")] == 7
    assert action_calls == 1
