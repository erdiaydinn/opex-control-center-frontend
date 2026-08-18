import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.engine_gateway import EngineEndpoint, EngineGatewayError, EngineProvider, RegisteredEngine
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    PrivacyLevel,
    TaskRisk,
    Modality,
)
from app.local_first_engine_runtime import LocalFirstProductionRuntime
from app.local_model_pool import (
    LocalCapability,
    LocalModelDeployment,
    load_local_model_catalog,
)
from app.paid_token_engine_gateway import PaidTokenExecutionContext
from app.teaching_intelligence import LearningObjective, TeachingMove
from app.teaching_runtime import TeachingGenerationRequest, generate_teaching_artifact

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"
NOW = datetime(2026, 8, 18, 10, 20, tzinfo=timezone.utc)


def _objective():
    return LearningObjective(
        objective_id="objective:nsfr-definition",
        domain="operations",
        title="Explain NSFR from governed source material",
        source_refs=("knowledge://ops/nsfr/v1",),
        required_mastery_score=0.85,
    )


def _context():
    return PaidTokenExecutionContext(
        subject_user_ref="user:teacher-learner",
        tenant_ref="tenant:academy-a",
        billing_cycle_ref="2026-08",
        requested_at=NOW,
    )


def _deployment(**updates):
    payload = dict(
        deployment_id="gpt-oss-teacher-local",
        model_family="gpt-oss-20b",
        model_id="gpt-oss:20b",
        runtime="OLLAMA",
        endpoint_ref="runtime://ollama/gpt-oss-teacher-local",
        enabled=True,
        runtime_reachable=True,
        benchmark_score=0.91,
        benchmark_evidence_ref="benchmark://teacher/local/gpt-oss/1",
        observed_capabilities=frozenset(
            {
                LocalCapability.TEXT,
                LocalCapability.REASONING,
                LocalCapability.STRUCTURED_OUTPUT,
            }
        ),
        max_context_tokens=32768,
    )
    payload.update(updates)
    return LocalModelDeployment(**payload)


def _registration():
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id="gpt-oss-teacher-local",
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
            benchmark_score=0.91,
            benchmark_evidence_ref="benchmark://teacher/local/gpt-oss/1",
            independent_provider_key="local:gpt-oss-20b",
        ),
        endpoint=EngineEndpoint(
            engine_id="gpt-oss-teacher-local",
            provider=EngineProvider.OLLAMA,
            model_id="gpt-oss:20b",
            base_url="http://127.0.0.1:11434",
        ),
    )


class _FrontierMustNotRun:
    async def invoke_primary(self, **kwargs):
        raise AssertionError("paid frontier must not run when qualified local teacher exists")


class _AdminDeniedFrontier:
    def __init__(self):
        self.calls = 0

    async def invoke_primary(self, **kwargs):
        self.calls += 1
        raise EngineGatewayError(
            "paid_token_not_authorized:paid_token_active_platform_admin_grant_missing"
        )


def _runtime(handler, *, deployment=None, frontier=None):
    return LocalFirstProductionRuntime(
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(deployment or _deployment(),),
        local_registrations=(_registration(),),
        frontier_runtime=frontier or _FrontierMustNotRun(),
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={},
    )


def test_teaching_uses_qualified_local_model_and_does_not_retain_grounded_excerpt():
    captured = {}
    secret_excerpt = "PRIVATE_GROUNDED_EXCERPT_97f1: NSFR is governed by the supplied definition."

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"content": "NSFR'yi kısa ve kaynakla uyumlu biçimde açıkla."},
                "prompt_eval_count": 30,
                "eval_count": 12,
            },
        )

    result = asyncio.run(
        generate_teaching_artifact(
            runtime=_runtime(handler),
            request=TeachingGenerationRequest(
                learner_ref="learner:1",
                objective=_objective(),
                move=TeachingMove.EXPLAIN,
                preferred_language="tr-TR",
                privacy=PrivacyLevel.INTERNAL,
            ),
            grounded_context=secret_excerpt,
            context=_context(),
        )
    )

    assert result.inference.paid_frontier_used is False
    assert result.inference.local_receipt is not None
    assert result.inference.local_receipt.engine_id == "gpt-oss-teacher-local"
    assert result.source_refs == ("knowledge://ops/nsfr/v1",)
    assert result.grounded_context_retained is False
    assert result.prompt_retained is False
    assert secret_excerpt in captured["payload"]["messages"][0]["content"]
    assert secret_excerpt not in result.model_dump_json()


def test_teaching_local_failure_cannot_bypass_admin_paid_token_gate():
    frontier = _AdminDeniedFrontier()

    async def unused_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("disabled local deployment must not be invoked")

    runtime = _runtime(
        unused_handler,
        deployment=_deployment(
            enabled=False,
            runtime_reachable=False,
            benchmark_score=None,
            benchmark_evidence_ref=None,
            observed_capabilities=frozenset(),
        ),
        frontier=frontier,
    )

    with pytest.raises(
        EngineGatewayError,
        match="paid_token_active_platform_admin_grant_missing",
    ):
        asyncio.run(
            generate_teaching_artifact(
                runtime=runtime,
                request=TeachingGenerationRequest(
                    learner_ref="learner:2",
                    objective=_objective(),
                    move=TeachingMove.TRANSFER_CHALLENGE,
                    preferred_language="tr-TR",
                ),
                grounded_context="Verified source context.",
                context=_context(),
            )
        )
    assert frontier.calls == 1


def test_feedback_requires_ephemeral_learner_response_and_rejects_verbatim_echo():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        marker = "I think NSFR means only refund failures forever"
        assert marker in prompt
        return httpx.Response(
            200,
            json={
                "message": {"content": f"Your response was: {marker}"},
                "prompt_eval_count": 25,
                "eval_count": 10,
            },
        )

    request = TeachingGenerationRequest(
        learner_ref="learner:3",
        objective=_objective(),
        move=TeachingMove.FEEDBACK,
        preferred_language="en-US",
    )
    with pytest.raises(ValueError, match="feedback_requires_learner_response"):
        asyncio.run(
            generate_teaching_artifact(
                runtime=_runtime(handler),
                request=request,
                grounded_context="Verified source context.",
                context=_context(),
            )
        )

    with pytest.raises(RuntimeError, match="raw_learner_response_echo_forbidden"):
        asyncio.run(
            generate_teaching_artifact(
                runtime=_runtime(handler),
                request=request,
                grounded_context="Verified source context.",
                context=_context(),
                learner_response="I think NSFR means only refund failures forever",
            )
        )


def test_source_gap_is_explicit_instead_of_fabricating_teaching_truth():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": "SOURCE_GAP: supplied evidence does not support that claim."},
                "prompt_eval_count": 12,
                "eval_count": 7,
            },
        )

    result = asyncio.run(
        generate_teaching_artifact(
            runtime=_runtime(handler),
            request=TeachingGenerationRequest(
                learner_ref="learner:4",
                objective=_objective(),
                move=TeachingMove.CONTRASTIVE_EXAMPLE,
                preferred_language="en-US",
            ),
            grounded_context="The source does not define the requested edge case.",
            context=_context(),
        )
    )
    assert result.source_gap_detected is True
    assert result.content.startswith("SOURCE_GAP")
