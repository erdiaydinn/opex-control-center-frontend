from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

_TOKEN_RE = re.compile(r"[\wÇĞİÖŞÜçğıöşü-]+", re.UNICODE)
_PLACEHOLDER_RE = re.compile(r"\b(?:todo|tbd|lorem ipsum|placeholder|example only|dummy)\b", re.IGNORECASE)
_LEGAL_RE = re.compile(
    r"\b(?:kanunen|mevzuata göre|yasal olarak|resm[iî]\s+gazete|kanun|yönetmelik|tebliğ)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TeacherQualityResult:
    accepted: bool
    score: int
    violations: tuple[str, ...]
    review_sha256: str


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(text)]


def _normalized_principles(principles: Sequence[object]) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in principles if str(item).strip())


def _fingerprint(
    *,
    critique: str,
    improved_answer: str,
    principles: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> str:
    payload = {
        "critique": critique,
        "improved_answer": improved_answer,
        "principles": list(principles),
        "evidence_ids": list(evidence_ids),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_teacher_review(
    *,
    model_answer: str,
    review: Mapping[str, object],
    evidence_ids: Iterable[str] = (),
) -> TeacherQualityResult:
    """Evaluate a local teacher review before it can contribute to SFT data.

    The rubric is deterministic and intentionally conservative: a human approval cannot
    make a structurally weak, placeholder, ungrounded legal, or unchanged teacher answer
    eligible for training. It does not attempt semantic truth scoring with another model.
    """

    critique = str(review.get("critique") or "").strip()
    improved_answer = str(review.get("improved_answer") or "").strip()
    raw_principles = review.get("principles")
    principles = _normalized_principles(raw_principles if isinstance(raw_principles, list) else ())
    evidence = tuple(sorted({str(item).strip() for item in evidence_ids if str(item).strip()}))

    violations: list[str] = []
    if len(critique) < 20:
        violations.append("teacher_critique_too_short")
    if len(set(_tokens(critique))) < 6:
        violations.append("teacher_critique_too_thin")
    if len(improved_answer) < 30:
        violations.append("teacher_answer_too_short")
    if len(set(_tokens(improved_answer))) < 8:
        violations.append("teacher_answer_too_thin")
    if _PLACEHOLDER_RE.search(critique) or _PLACEHOLDER_RE.search(improved_answer):
        violations.append("teacher_placeholder_not_allowed")
    if len(principles) < 2:
        violations.append("teacher_principles_insufficient")
    elif any(len(set(_tokens(item))) < 3 for item in principles):
        violations.append("teacher_principle_too_thin")

    original = model_answer.strip().casefold()
    if original and improved_answer.casefold() == original:
        violations.append("teacher_answer_unchanged")

    if _LEGAL_RE.search(improved_answer) and not evidence:
        violations.append("teacher_legal_claim_without_evidence")

    penalties = {
        "teacher_critique_too_short": 30,
        "teacher_critique_too_thin": 25,
        "teacher_answer_too_short": 45,
        "teacher_answer_too_thin": 35,
        "teacher_placeholder_not_allowed": 100,
        "teacher_principles_insufficient": 30,
        "teacher_principle_too_thin": 20,
        "teacher_answer_unchanged": 60,
        "teacher_legal_claim_without_evidence": 100,
    }
    score = max(0, 100 - sum(penalties[item] for item in violations))
    return TeacherQualityResult(
        accepted=not violations,
        score=score,
        violations=tuple(violations),
        review_sha256=_fingerprint(
            critique=critique,
            improved_answer=improved_answer,
            principles=principles,
            evidence_ids=evidence,
        ),
    )
