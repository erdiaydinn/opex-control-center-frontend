"""Competing-hypothesis ranking for EAY Jarvis.

Jarvis should not anchor on the first plausible explanation (rain, marathon,
promotion, staffing, availability, platform incident, etc.). This module forces
candidate explanations to carry both supporting and refuting evidence and makes
uncertainty explicit. Rankings are decision support, never causal proof.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

HYPOTHESIS_INTELLIGENCE_CONTRACT = "eay-hypothesis-intelligence-v1"


class EvidenceDirection(str, Enum):
    SUPPORT = "support"
    REFUTE = "refute"
    NEUTRAL = "neutral"


class HypothesisEvidence(BaseModel):
    evidence_ref: str = Field(min_length=1, max_length=500)
    direction: EvidenceDirection
    weight: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)
    independent_source_key: str = Field(min_length=1, max_length=240)

    @property
    def effective_weight(self) -> float:
        return self.weight * self.source_quality


class HypothesisCandidate(BaseModel):
    hypothesis_id: str = Field(min_length=1, max_length=180)
    label: str = Field(min_length=1, max_length=500)
    evidence: tuple[HypothesisEvidence, ...] = Field(min_length=1)
    missing_tests: tuple[str, ...] = ()


class HypothesisAssessment(BaseModel):
    hypothesis_id: str
    label: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    support_weight: float = Field(ge=0.0)
    refute_weight: float = Field(ge=0.0)
    independent_source_count: int = Field(ge=1)
    counterevidence_present: bool
    causal_proof: bool = False
    blockers: tuple[str, ...] = ()
    missing_tests: tuple[str, ...] = ()

    @model_validator(mode="after")
    def prohibit_causal_claim(self) -> "HypothesisAssessment":
        if self.causal_proof:
            raise ValueError("hypothesis_engine_cannot_assert_causality")
        return self


class HypothesisRanking(BaseModel):
    contract: str = HYPOTHESIS_INTELLIGENCE_CONTRACT
    assessments: tuple[HypothesisAssessment, ...]
    leading_hypothesis_id: str | None = None
    leading_margin: float | None = None
    decisive: bool = False
    requires_more_evidence: bool = True
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ("ranked_hypothesis_is_not_causal_proof",)


def assess_hypothesis(candidate: HypothesisCandidate) -> HypothesisAssessment:
    support = sum(
        item.effective_weight
        for item in candidate.evidence
        if item.direction is EvidenceDirection.SUPPORT
    )
    refute = sum(
        item.effective_weight
        for item in candidate.evidence
        if item.direction is EvidenceDirection.REFUTE
    )
    informative_total = support + refute
    independent_sources = len({item.independent_source_key for item in candidate.evidence})
    coverage = min(independent_sources / 3.0, 1.0)

    if informative_total == 0:
        score = 0.0
        confidence = 0.0
    else:
        score = (support - refute) / informative_total
        directional_confidence = max(support - refute, 0.0) / informative_total
        confidence = directional_confidence * coverage

    blockers: list[str] = []
    counterevidence_present = refute > 0
    if not counterevidence_present:
        blockers.append("counterevidence_missing")
    if independent_sources < 2:
        blockers.append("independent_source_diversity_low")
    if candidate.missing_tests:
        blockers.append("falsification_tests_pending")

    return HypothesisAssessment(
        hypothesis_id=candidate.hypothesis_id,
        label=candidate.label,
        score=round(max(min(score, 1.0), -1.0), 6),
        confidence=round(max(min(confidence, 1.0), 0.0), 6),
        support_weight=round(support, 6),
        refute_weight=round(refute, 6),
        independent_source_count=independent_sources,
        counterevidence_present=counterevidence_present,
        blockers=tuple(blockers),
        missing_tests=candidate.missing_tests,
    )


def rank_hypotheses(
    candidates: list[HypothesisCandidate] | tuple[HypothesisCandidate, ...],
) -> HypothesisRanking:
    if not candidates:
        return HypothesisRanking(
            assessments=(),
            leading_hypothesis_id=None,
            leading_margin=None,
            decisive=False,
            requires_more_evidence=True,
            blockers=("hypothesis_candidates_missing",),
        )

    assessments = sorted(
        (assess_hypothesis(candidate) for candidate in candidates),
        key=lambda item: (-item.confidence, -item.score, item.hypothesis_id),
    )
    leader = assessments[0]
    runner_up_confidence = assessments[1].confidence if len(assessments) > 1 else 0.0
    margin = round(leader.confidence - runner_up_confidence, 6)

    blockers: list[str] = []
    if leader.confidence < 0.65:
        blockers.append("leading_hypothesis_confidence_below_decision_threshold")
    if margin < 0.15 and len(assessments) > 1:
        blockers.append("competing_hypotheses_too_close")
    blockers.extend(leader.blockers)

    decisive = not blockers and leader.score > 0
    return HypothesisRanking(
        assessments=tuple(assessments),
        leading_hypothesis_id=leader.hypothesis_id,
        leading_margin=margin,
        decisive=decisive,
        requires_more_evidence=not decisive,
        blockers=tuple(dict.fromkeys(blockers)),
    )
