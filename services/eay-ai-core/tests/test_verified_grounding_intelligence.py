from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.frontier_supremacy_intelligence import EngineDomainBenchmark, SupremacyDomain
from app.intelligence_router import (
    IntelligenceRoutingPlan,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.research_engine import (
    ResearchEvidence,
    ResearchQuestion,
    ResearchRisk,
    ResearchRole,
    SourceTier,
)
from app.verified_grounding_intelligence import (
    GroundedEvidenceRecord,
    GroundingDisposition,
    VerifiedGroundedSupremacyRequest,
    VerifiedGroundingBundle,
    build_verified_grounding_bundle,
    execute_verified_grounded_frontier_supremacy,
)

NOW = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)


def _question(text: str = "Is the verified market claim currently supported?") -> ResearchQuestion:
    return ResearchQuestion(
        question_id="research-1",
        question=text,
        risk=ResearchRisk.HIGH,
        as_of=NOW,
        requires_current_information=True,
        minimum_independent_sources=2,
    )


def _evidence(
    evidence_id: str,
    publisher: str,
    *,
    tier: SourceTier,
    value: str,
    supports: bool = True,
    contradicts: bool = False,
    published_at: datetime | None = None,
) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=evidence_id,
        claim_key="claim-a",
        claim_value=value,
        source_url=f"https://{publisher}.example/evidence/{evidence_id}",
        source_domain=f"{publisher}.example",
        source_tier=tier,
        publisher_key=publisher,
        published_at=published_at or (NOW - timedelta(days=1)),
        fetched_at=NOW,
        supports_claim=supports,
        contradicts_claim=contradicts,
        evidence_ref=f"evidence://{publisher}/{evidence_id}",
    )


def _record(
    evidence: ResearchEvidence,
    roles: tuple[ResearchRole, ...],
    *,
    tenant: str = "tenant-a",
    company: str = "company-a",
    question_id: str = "research-1",
) -> GroundedEvidenceRecord:
    return GroundedEvidenceRecord(
        tenant_id=tenant,
        company_id=company,
        question_id=question_id,
        evidence=evidence,
        observed_roles=roles,
    )


def _ready_records() -> list[GroundedEvidenceRecord]:
    return [
        _record(
            _evidence("official", "official", tier=SourceTier.PRIMARY, value="Official evidence supports A"),
            (ResearchRole.PRIMARY_SOURCE, ResearchRole.TEMPORAL_UPDATE),
        ),
        _record(
            _evidence(
                "independent-1",
                "authority",
                tier=SourceTier.AUTHORITATIVE_SECONDARY,
                value="Independent authority corroborates A",
            ),
            (ResearchRole.CORROBORATION, ResearchRole.CONTRADICTION),
        ),
        _record(
            _evidence(
                "independent-2",
                "reputable",
                tier=SourceTier.REPUTABLE_SECONDARY,
                value="Third publisher independently supports A",
            ),
            (ResearchRole.CORROBORATION,),
        ),
    ]


def _bundle(records: list[GroundedEvidenceRecord] | None = None, question: ResearchQuestion | None = None):
    return build_verified_grounding_bundle(
        tenant_id="tenant-a",
        company_id="company-a",
        question=question or _question(),
        claim_keys=("claim-a",),
        records=records or _ready_records(),
    )


def test_verified_grounding_requires_primary_independence_contradiction_and_temporal_roles() -> None:
    bundle = _bundle()
    assert bundle.disposition is GroundingDisposition.READY
    assert bundle.blockers == ()
    assert bundle.primary_source_count == 1
    assert bundle.independent_publishers == 3
    assert len(bundle.evidence_refs) == 3
    assert ResearchRole.PRIMARY_SOURCE in bundle.observed_roles
    assert ResearchRole.CONTRADICTION in bundle.observed_roles
    assert ResearchRole.TEMPORAL_UPDATE in bundle.observed_roles
    assert "Official evidence supports A" in bundle.grounding_context
    assert "untrusted" not in bundle.grounding_context.casefold()
    assert bundle.execution_authority_granted is False
    assert bundle.company_truth_promoted is False


def test_missing_contradiction_search_role_forces_hold() -> None:
    records = _ready_records()
    records[1] = records[1].model_copy(update={"observed_roles": (ResearchRole.CORROBORATION,)})
    bundle = _bundle(records)
    assert bundle.disposition is GroundingDisposition.HOLD
    assert "verified_grounding_required_role_missing:contradiction" in bundle.blockers


def test_future_published_evidence_is_excluded_and_blocks_as_of_grounding() -> None:
    records = _ready_records()
    records[2] = _record(
        _evidence(
            "future",
            "future-publisher",
            tier=SourceTier.REPUTABLE_SECONDARY,
            value="Evidence not yet available",
            published_at=NOW + timedelta(days=1),
        ),
        (ResearchRole.CORROBORATION,),
    )
    bundle = _bundle(records)
    assert bundle.disposition is GroundingDisposition.HOLD
    assert any("research_evidence_not_available_as_of" in code for code in bundle.blockers)
    assert "Evidence not yet available" not in bundle.grounding_context


def test_material_contradiction_forces_contested_not_confident_synthesis() -> None:
    records = _ready_records()
    records[2] = _record(
        _evidence(
            "contradiction",
            "reputable",
            tier=SourceTier.REPUTABLE_SECONDARY,
            value="Independent evidence contradicts A",
            supports=False,
            contradicts=True,
        ),
        (ResearchRole.CORROBORATION, ResearchRole.CONTRADICTION),
    )
    bundle = _bundle(records)
    assert bundle.disposition is GroundingDisposition.CONTESTED
    assert "verified_grounding_claim_contested" in bundle.blockers


def test_quantitative_research_requires_quantitative_check_role() -> None:
    question = _question("What is the current cost impact and margin rate?")
    bundle = _bundle(question=question)
    assert bundle.disposition is GroundingDisposition.HOLD
    assert "verified_grounding_required_role_missing:quantitative_check" in bundle.blockers

    records = _ready_records()
    records[2] = records[2].model_copy(
        update={"observed_roles": (ResearchRole.CORROBORATION, ResearchRole.QUANTITATIVE_CHECK)}
    )
    accepted = _bundle(records, question)
    assert accepted.disposition is GroundingDisposition.READY


def test_cross_tenant_company_and_question_evidence_are_rejected() -> None:
    records = _ready_records()
    records[0] = records[0].model_copy(update={"tenant_id": "tenant-b"})
    with pytest.raises(ValueError, match="verified_grounding_cross_tenant_evidence_forbidden"):
        _bundle(records)

    records = _ready_records()
    records[0] = records[0].model_copy(update={"company_id": "company-b"})
    with pytest.raises(ValueError, match="verified_grounding_cross_company_evidence_forbidden"):
        _bundle(records)

    records = _ready_records()
    records[0] = records[0].model_copy(update={"question_id": "other-question"})
    with pytest.raises(ValueError, match="verified_grounding_question_identity_mismatch"):
        _bundle(records)


def test_grounding_fingerprint_is_tamper_evident() -> None:
    bundle = _bundle()
    raw = bundle.model_dump(mode="json")
    raw["grounding_context"] += "\nUNVERIFIED INSERTION"
    with pytest.raises(ValidationError, match="verified_grounding_fingerprint_mismatch"):
        VerifiedGroundingBundle.model_validate(raw)


@dataclass
class Receipt:
    engine_id: str
    output_text: str


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def plan(self, task: IntelligenceTask) -> IntelligenceRoutingPlan:
        return IntelligenceRoutingPlan(
            task_id=task.task_id,
            primary_engine_id="sol",
            critic_engine_ids=("claude", "gemini"),
            council_required=True,
            execution_permitted=True,
        )

    async def invoke_primary(self, *, task: IntelligenceTask, prompt: str) -> Receipt:
        self.calls.append(prompt)
        if "SYNTHESIZER" in prompt:
            return Receipt("sol", "Grounded synthesis")
        return Receipt("sol", "Grounded initial analysis")

    async def invoke_routed_engines(
        self, *, task: IntelligenceTask, prompt: str
    ) -> tuple[Receipt, ...]:
        self.calls.append(prompt)
        if "FINAL VERIFIER" in prompt:
            return (
                Receipt("sol", "primary"),
                Receipt("claude", "VERDICT: PASS\nSources support the conclusion."),
                Receipt("gemini", "VERDICT: PASS\nNo unresolved contradiction."),
            )
        return (
            Receipt("sol", "primary"),
            Receipt("claude", "Independent source-grounded critique"),
            Receipt("gemini", "Independent falsification attempt"),
        )


def _benchmarks() -> tuple[EngineDomainBenchmark, ...]:
    return tuple(
        EngineDomainBenchmark(
            engine_id=engine_id,
            provider_key=provider,
            domain=SupremacyDomain.DEEP_RESEARCH,
            normalized_frontier_score=1.0,
            sample_count=250,
            measured_at=NOW,
            evidence_ref=f"benchmark://deep-research/{engine_id}",
            independent_evaluator=True,
        )
        for engine_id, provider in (
            ("sol", "openai"),
            ("claude", "anthropic"),
            ("gemini", "google"),
        )
    )


def _task() -> IntelligenceTask:
    return IntelligenceTask(
        task_id="deep-research-task",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        requires_long_horizon=True,
        requires_independent_critique=True,
    )


@pytest.mark.asyncio
async def test_deep_research_supremacy_uses_only_sealed_verified_grounding() -> None:
    gateway = FakeGateway()
    bundle = _bundle()
    result = await execute_verified_grounded_frontier_supremacy(
        gateway=gateway,
        request=VerifiedGroundedSupremacyRequest(
            tenant_id="tenant-a",
            company_id="company-a",
            domain=SupremacyDomain.DEEP_RESEARCH,
            task=_task(),
            problem="Determine whether claim A is supported and explain uncertainty.",
            benchmarks=_benchmarks(),
            grounding=bundle,
        ),
    )
    assert result.supremacy.decision_ready is True
    assert result.supremacy.final_answer == "Grounded synthesis"
    assert result.grounding_fingerprint == bundle.fingerprint
    assert result.execution_authority_granted is False
    assert result.company_truth_promoted is False
    assert result.superiority_claim_allowed is False
    combined = "\n".join(gateway.calls)
    assert "Official evidence supports A" in combined
    assert all(ref in combined for ref in bundle.evidence_refs)


def test_non_ready_or_cross_company_bundle_cannot_enter_supremacy() -> None:
    records = _ready_records()
    records[1] = records[1].model_copy(update={"observed_roles": (ResearchRole.CORROBORATION,)})
    hold = _bundle(records)
    with pytest.raises(ValidationError, match="verified_grounding_bundle_not_ready"):
        VerifiedGroundedSupremacyRequest(
            tenant_id="tenant-a",
            company_id="company-a",
            domain=SupremacyDomain.DEEP_RESEARCH,
            task=_task(),
            problem="Research claim A",
            benchmarks=_benchmarks(),
            grounding=hold,
        )

    ready = _bundle()
    with pytest.raises(ValidationError, match="verified_grounding_cross_company_bundle_forbidden"):
        VerifiedGroundedSupremacyRequest(
            tenant_id="tenant-a",
            company_id="company-b",
            domain=SupremacyDomain.DEEP_RESEARCH,
            task=_task(),
            problem="Research claim A",
            benchmarks=_benchmarks(),
            grounding=ready,
        )
