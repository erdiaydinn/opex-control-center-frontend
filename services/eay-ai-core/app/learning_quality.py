from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

_TOKEN_RE = re.compile(r"[\wÇĞİÖŞÜçğıöşü-]+", re.UNICODE)
_PLACEHOLDER_RE = re.compile(r"\b(?:todo|tbd|lorem ipsum|placeholder|example only)\b", re.IGNORECASE)


@dataclass(frozen=True)
class LearningQualityResult:
    accepted: bool
    score: int
    violations: tuple[str, ...]
    target_sha256: str


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(text)]


def evaluate_learning_example(
    *,
    user_message: str,
    model_answer: str,
    target_answer: str,
    reason: str,
    teacher_reviewed: bool,
    human_approved: bool,
    evidence_ids: Iterable[str] = (),
    legal_claim: bool = False,
    privacy_safe: bool = True,
) -> LearningQualityResult:
    violations: list[str] = []
    user_message = user_message.strip()
    model_answer = model_answer.strip()
    target_answer = target_answer.strip()
    reason = reason.strip()

    if not human_approved:
        violations.append("human_approval_required")
    if not privacy_safe:
        violations.append("privacy_review_required")
    if len(user_message) < 3:
        violations.append("user_message_too_short")
    if len(target_answer) < 20:
        violations.append("target_answer_too_short")
    if not reason:
        violations.append("learning_reason_required")
    if _PLACEHOLDER_RE.search(target_answer):
        violations.append("placeholder_target_not_allowed")
    if len(set(_tokens(target_answer))) < 6:
        violations.append("target_content_too_thin")
    if model_answer and target_answer.casefold() == model_answer.casefold() and not teacher_reviewed:
        violations.append("unchanged_model_answer_without_teacher_review")

    evidence = tuple(sorted({str(item).strip() for item in evidence_ids if str(item).strip()}))
    if legal_claim and not evidence:
        violations.append("legal_claim_without_evidence")

    penalties = {
        "human_approval_required": 100,
        "privacy_review_required": 100,
        "legal_claim_without_evidence": 100,
        "placeholder_target_not_allowed": 70,
        "target_answer_too_short": 45,
        "target_content_too_thin": 35,
        "user_message_too_short": 25,
        "learning_reason_required": 25,
        "unchanged_model_answer_without_teacher_review": 20,
    }
    score = max(0, 100 - sum(penalties[item] for item in violations))
    return LearningQualityResult(
        accepted=not violations,
        score=score,
        violations=tuple(violations),
        target_sha256=hashlib.sha256(target_answer.encode("utf-8")).hexdigest(),
    )
