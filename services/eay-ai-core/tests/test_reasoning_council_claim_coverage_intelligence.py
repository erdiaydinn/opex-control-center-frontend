import asyncio
import json

import httpx

from app.engine_gateway import EngineEndpoint, EngineGateway, EngineProvider, RegisteredEngine
from app.intelligence_router import EngineClass, IntelligenceEngine, IntelligenceTask, Modality, PrivacyLevel, TaskComplexity, TaskRisk
from app.reasoning_council_executor import ClaimQuestion, CouncilExecutionInput, EvidenceItem, execute_reasoning_council


def _engine(engine_id, provider, host, secret_ref, score):
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id=engine_id,
            engine_class=EngineClass.FRONTIER,
            modalities=(Modality.TEXT,),
            local_processing=False,
            maximum_privacy=PrivacyLevel.INTERNAL,
            maximum_risk=TaskRisk.HIGH,
            exact_adapter_verified=True,
            production_enabled=True,
            benchmark_score=score,
            benchmark_evidence_ref=f"eval://{engine_id}",
            independent_provider_key=engine_id,
        ),
        endpoint=EngineEndpoint(
            engine_id=engine_id,
            provider=provider,
            model_id="gpt-5.6" if engine_id == "openai" else "claude-opus-4-8",
            base_url=host,
            secret_ref=secret_ref,
        ),
    )


def test_claim_refuted_by_every_engine_cannot_disappear_from_final_readiness():
    evaluations = {
        "evaluations": [
            {"claim_key": "claim-a", "stance": "support", "confidence": 0.9, "evidence_refs": ["evidence://1"]},
            {"claim_key": "claim-b", "stance": "refute", "confidence": 0.9, "evidence_refs": ["evidence://1"]},
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        text = json.dumps(evaluations)
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]})
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})

    gateway = EngineGateway(
        [
            _engine("openai", EngineProvider.OPENAI_RESPONSES, "https://api.openai.com", "env:OPENAI_API_KEY", 0.99),
            _engine("anthropic", EngineProvider.ANTHROPIC_MESSAGES, "https://api.anthropic.com", "env:ANTHROPIC_API_KEY", 0.98),
        ],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b"},
    )
    payload = CouncilExecutionInput(
        task=IntelligenceTask(
            task_id="coverage",
            complexity=TaskComplexity.HARD,
            risk=TaskRisk.HIGH,
            privacy=PrivacyLevel.INTERNAL,
            modalities=(Modality.TEXT,),
        ),
        objective="Evaluate both claims.",
        claims=(
            ClaimQuestion(claim_key="claim-a", statement="A is true", allowed_evidence_refs=("evidence://1",)),
            ClaimQuestion(claim_key="claim-b", statement="B is true", allowed_evidence_refs=("evidence://1",)),
        ),
        evidence=(EvidenceItem(evidence_ref="evidence://1", content="Governed evidence"),),
    )
    result = asyncio.run(execute_reasoning_council(gateway=gateway, payload=payload))

    assert result.decision_ready is False
    assert "council_executor_claim_without_supported_proposal:claim-b" in result.blockers
