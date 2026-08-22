from datetime import UTC, datetime, timedelta

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
    build_verified_grounding_bundle,
)

NOW = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)


def _evidence(evidence_id: str, publisher: str, tier: SourceTier) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=evidence_id,
        claim_key="claim-a",
        claim_value="claim A is supported",
        source_url=f"https://{publisher}.example/{evidence_id}",
        source_domain=f"{publisher}.example",
        source_tier=tier,
        publisher_key=publisher,
        published_at=NOW - timedelta(days=1),
        fetched_at=NOW,
        supports_claim=True,
        evidence_ref=f"evidence://{publisher}/{evidence_id}",
    )


def test_two_source_quorum_cannot_be_misrepresented_as_frontier_deep_research_grounding() -> None:
    question = ResearchQuestion(
        question_id="q-two-sources",
        question="Is claim A currently supported?",
        risk=ResearchRisk.HIGH,
        as_of=NOW,
        requires_current_information=True,
        minimum_independent_sources=2,
    )
    records = [
        GroundedEvidenceRecord(
            tenant_id="tenant-a",
            company_id="company-a",
            question_id=question.question_id,
            evidence=_evidence("official", "official", SourceTier.PRIMARY),
            observed_roles=(ResearchRole.PRIMARY_SOURCE, ResearchRole.TEMPORAL_UPDATE),
        ),
        GroundedEvidenceRecord(
            tenant_id="tenant-a",
            company_id="company-a",
            question_id=question.question_id,
            evidence=_evidence("independent", "authority", SourceTier.AUTHORITATIVE_SECONDARY),
            observed_roles=(ResearchRole.CORROBORATION, ResearchRole.CONTRADICTION),
        ),
    ]

    bundle = build_verified_grounding_bundle(
        tenant_id="tenant-a",
        company_id="company-a",
        question=question,
        claim_keys=("claim-a",),
        records=records,
    )

    assert bundle.independent_publishers == 2
    assert len(bundle.evidence_refs) == 2
    assert bundle.disposition is GroundingDisposition.HOLD
    assert "verified_grounding_three_evidence_refs_required" in bundle.blockers
