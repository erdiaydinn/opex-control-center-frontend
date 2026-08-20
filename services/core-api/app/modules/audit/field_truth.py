from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from .control_contracts import AuditQuestionControl, EvidenceModality
from .schemas import AuditDecision, StrictModel

AnswerSelection = Literal["YES", "NO", "NOT_APPLICABLE"]
CompletionState = Literal["COMPLETE", "INCOMPLETE"]


class AuditApplicabilityEvidence(StrictModel):
    evaluated: bool = False
    applies: bool | None = None
    source_refs: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_applicability(self) -> AuditApplicabilityEvidence:
        if not self.evaluated and self.applies is not None:
            raise ValueError("unevaluated applicability cannot assert applies")
        if self.evaluated and self.applies is None:
            raise ValueError("evaluated applicability requires applies")
        if self.evaluated and not self.source_refs:
            raise ValueError("evaluated applicability requires source_refs")
        return self


class AuditEvidenceObservation(StrictModel):
    modalities: tuple[EvidenceModality, ...] = Field(default=(), max_length=7)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=50)
    privacy_verified_media_refs: tuple[str, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def validate_observation(self) -> AuditEvidenceObservation:
        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("observed evidence modalities must be unique")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        if not set(self.privacy_verified_media_refs).issubset(set(self.evidence_refs)):
            raise ValueError("privacy-verified media refs must also be evidence refs")
        return self


class AuditItemTruth(StrictModel):
    item_key: str
    decision: AuditDecision
    answer: AnswerSelection | None
    reason_code: str
    required_follow_up: str | None = None


def _evidence_is_sufficient(
    control: AuditQuestionControl,
    observation: AuditEvidenceObservation,
) -> bool:
    contract = control.evidence_contract
    if contract is None:
        return bool(set(observation.modalities) & set(control.evidence_modalities))

    observed = set(observation.modalities)
    if not set(contract.required_modalities).issubset(observed):
        return False
    if contract.any_of_modalities and not (
        observed & set(contract.any_of_modalities)
    ):
        return False
    if len(observation.evidence_refs) < contract.minimum_evidence_refs:
        return False

    if contract.require_privacy_verified_media:
        media_refs_required = bool(
            {"VISUAL", "VIDEO"}
            & (
                set(contract.required_modalities)
                | set(contract.any_of_modalities)
            )
        )
        if media_refs_required:
            if not observation.evidence_refs:
                return False
            if not observation.privacy_verified_media_refs:
                return False
    return True


def evaluate_question_truth(
    control: AuditQuestionControl,
    *,
    answer: AnswerSelection | None,
    observation: AuditEvidenceObservation,
    applicability: AuditApplicabilityEvidence | None = None,
) -> AuditItemTruth:
    """Resolve one audit answer without deriving polarity from natural-language text."""

    semantics = control.answer_semantics
    if semantics is None:
        return AuditItemTruth(
            item_key=control.item_key,
            decision="REVIEW_REQUIRED",
            answer=answer,
            reason_code="MISSING_ANSWER_SEMANTICS",
            required_follow_up="Bind a versioned answer semantic contract.",
        )

    applicability = applicability or AuditApplicabilityEvidence()
    if applicability.evaluated and applicability.applies is False:
        if semantics.allow_not_applicable:
            return AuditItemTruth(
                item_key=control.item_key,
                decision="NOT_APPLICABLE",
                answer="NOT_APPLICABLE",
                reason_code="APPLICABILITY_PROVEN_FALSE",
            )
        return AuditItemTruth(
            item_key=control.item_key,
            decision="REVIEW_REQUIRED",
            answer=answer,
            reason_code="APPLICABILITY_CONFLICT",
            required_follow_up="Question does not permit N/A for this standard version.",
        )

    if answer == "NOT_APPLICABLE":
        if (
            semantics.allow_not_applicable
            and applicability.evaluated
            and applicability.applies is False
        ):
            return AuditItemTruth(
                item_key=control.item_key,
                decision="NOT_APPLICABLE",
                answer=answer,
                reason_code="APPLICABILITY_PROVEN_FALSE",
            )
        return AuditItemTruth(
            item_key=control.item_key,
            decision="REVIEW_REQUIRED",
            answer=answer,
            reason_code="UNPROVEN_NOT_APPLICABLE",
            required_follow_up=(
                "Missing evidence is not N/A; prove non-applicability or collect evidence."
            ),
        )

    if answer is None:
        return AuditItemTruth(
            item_key=control.item_key,
            decision="INSUFFICIENT_EVIDENCE",
            answer=None,
            reason_code="ANSWER_MISSING",
            required_follow_up="Collect the required observation before scoring.",
        )

    if not _evidence_is_sufficient(control, observation):
        return AuditItemTruth(
            item_key=control.item_key,
            decision="INSUFFICIENT_EVIDENCE",
            answer=answer,
            reason_code="EVIDENCE_CONTRACT_NOT_SATISFIED",
            required_follow_up="Collect evidence required by the standard contract.",
        )

    if answer == semantics.expected_answer:
        return AuditItemTruth(
            item_key=control.item_key,
            decision="PASS",
            answer=answer,
            reason_code="EXPECTED_ANSWER_OBSERVED",
        )
    if answer == semantics.failure_answer:
        return AuditItemTruth(
            item_key=control.item_key,
            decision="FAIL",
            answer=answer,
            reason_code="FAILURE_ANSWER_OBSERVED",
        )
    return AuditItemTruth(
        item_key=control.item_key,
        decision="REVIEW_REQUIRED",
        answer=answer,
        reason_code="UNMAPPED_ANSWER",
    )


class AuditScoredItem(StrictModel):
    item_key: str
    decision: AuditDecision
    max_points: float = Field(gt=0, le=100000)


class AuditScoreSummary(StrictModel):
    completion_state: CompletionState
    total_items: int
    pass_count: int
    fail_count: int
    not_applicable_count: int
    insufficient_evidence_count: int
    review_required_count: int
    earned_points: float
    applicable_max_points: float
    provisional_score_pct: float | None
    final_score_pct: float | None


def score_audit_items(items: Iterable[AuditScoredItem]) -> AuditScoreSummary:
    rows = tuple(items)
    pass_count = sum(item.decision == "PASS" for item in rows)
    fail_count = sum(item.decision == "FAIL" for item in rows)
    na_count = sum(item.decision == "NOT_APPLICABLE" for item in rows)
    insufficient_count = sum(item.decision == "INSUFFICIENT_EVIDENCE" for item in rows)
    review_count = sum(item.decision == "REVIEW_REQUIRED" for item in rows)

    resolved_applicable = tuple(
        item for item in rows if item.decision in {"PASS", "FAIL"}
    )
    earned_points = sum(
        item.max_points for item in resolved_applicable if item.decision == "PASS"
    )
    applicable_max_points = sum(item.max_points for item in resolved_applicable)
    provisional = (
        round((earned_points / applicable_max_points) * 100, 2)
        if applicable_max_points > 0
        else None
    )

    complete = insufficient_count == 0 and review_count == 0
    final_score = provisional if complete else None
    return AuditScoreSummary(
        completion_state="COMPLETE" if complete else "INCOMPLETE",
        total_items=len(rows),
        pass_count=pass_count,
        fail_count=fail_count,
        not_applicable_count=na_count,
        insufficient_evidence_count=insufficient_count,
        review_required_count=review_count,
        earned_points=earned_points,
        applicable_max_points=applicable_max_points,
        provisional_score_pct=provisional,
        final_score_pct=final_score,
    )
