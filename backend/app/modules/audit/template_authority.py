"""Roadmap 23/60: versioned Audit template, scoring and branching authority.

This module owns deterministic template publication and audit-run evaluation.
It deliberately does not own media/evidence storage or the platform Audit Log.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import UUID, uuid4


class AuditTemplateError(ValueError):
    """Raised when an Audit template or run violates governed authority."""


class AuditTemplateStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class BranchOperator(StrEnum):
    EQ = "eq"
    NOT_EQ = "not_eq"
    IN = "in"
    NOT_IN = "not_in"


@dataclass(frozen=True, slots=True)
class BranchCondition:
    question_id: str
    operator: BranchOperator
    expected: Any

    def matches(self, answers: Mapping[str, Any]) -> bool:
        if self.question_id not in answers:
            return False
        actual = answers[self.question_id]
        if self.operator is BranchOperator.EQ:
            return actual == self.expected
        if self.operator is BranchOperator.NOT_EQ:
            return actual != self.expected
        if self.operator in (BranchOperator.IN, BranchOperator.NOT_IN):
            if not isinstance(self.expected, (tuple, list, set, frozenset)):
                raise AuditTemplateError(f"{self.operator.value} requires a collection expected value")
            contained = actual in self.expected
            return contained if self.operator is BranchOperator.IN else not contained
        raise AuditTemplateError(f"unsupported branch operator: {self.operator}")


@dataclass(frozen=True, slots=True)
class AuditQuestion:
    question_id: str
    prompt_key: str
    max_points: int
    scoring: tuple[tuple[str, int], ...]
    required: bool = True
    show_when: tuple[BranchCondition, ...] = ()

    def score_for(self, answer: Any) -> int:
        scoring = dict(self.scoring)
        key = _answer_key(answer)
        if key not in scoring:
            raise AuditTemplateError(
                f"answer {answer!r} has no governed score for visible question {self.question_id}"
            )
        return scoring[key]


@dataclass(frozen=True, slots=True)
class AuditTemplateRevision:
    tenant_id: str
    template_key: str
    revision: int
    status: AuditTemplateStatus
    questions: tuple[AuditQuestion, ...]
    created_by: str
    created_at: datetime
    content_hash: str
    published_by: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuditRunSnapshot:
    audit_run_id: UUID
    tenant_id: str
    template_key: str
    template_revision: int
    template_hash: str
    answers: tuple[tuple[str, Any], ...]
    visible_question_ids: tuple[str, ...]
    score_awarded: int
    score_possible: int
    score_percent: Decimal
    completed_by: str
    completed_at: datetime
    snapshot_hash: str


def draft_template(
    *,
    tenant_id: str,
    template_key: str,
    revision: int,
    questions: tuple[AuditQuestion, ...],
    created_by: str,
    created_at: datetime | None = None,
) -> AuditTemplateRevision:
    tenant_id = tenant_id.strip()
    template_key = template_key.strip()
    created_by = created_by.strip()
    if not tenant_id or not template_key or not created_by:
        raise AuditTemplateError("tenant_id, template_key and created_by are required")
    if revision < 1:
        raise AuditTemplateError("revision must be >= 1")
    _validate_questions(questions)
    created_at = _utc(created_at or datetime.now(UTC))
    draft = AuditTemplateRevision(
        tenant_id=tenant_id,
        template_key=template_key,
        revision=revision,
        status=AuditTemplateStatus.DRAFT,
        questions=questions,
        created_by=created_by,
        created_at=created_at,
        content_hash="",
    )
    return replace(draft, content_hash=_template_hash(draft))


def publish_template(
    draft: AuditTemplateRevision,
    *,
    actor: str,
    published_at: datetime | None = None,
) -> AuditTemplateRevision:
    if draft.status is not AuditTemplateStatus.DRAFT:
        raise AuditTemplateError("only a draft template revision can be published")
    actor = actor.strip()
    if not actor:
        raise AuditTemplateError("publishing actor is required")
    _validate_questions(draft.questions)
    expected_hash = _template_hash(draft)
    if draft.content_hash != expected_hash:
        raise AuditTemplateError("draft content hash is stale; rebuild the revision before publishing")
    return replace(
        draft,
        status=AuditTemplateStatus.PUBLISHED,
        published_by=actor,
        published_at=_utc(published_at or datetime.now(UTC)),
    )


def create_next_revision(
    published: AuditTemplateRevision,
    *,
    actor: str,
    questions: tuple[AuditQuestion, ...] | None = None,
    created_at: datetime | None = None,
) -> AuditTemplateRevision:
    if published.status is not AuditTemplateStatus.PUBLISHED:
        raise AuditTemplateError("next revision requires a published source revision")
    return draft_template(
        tenant_id=published.tenant_id,
        template_key=published.template_key,
        revision=published.revision + 1,
        questions=questions if questions is not None else published.questions,
        created_by=actor,
        created_at=created_at,
    )


def evaluate_audit(
    template: AuditTemplateRevision,
    answers: Mapping[str, Any],
    *,
    completed_by: str,
    completed_at: datetime | None = None,
    audit_run_id: UUID | None = None,
) -> AuditRunSnapshot:
    if template.status is not AuditTemplateStatus.PUBLISHED:
        raise AuditTemplateError("audit runs require an exact published template revision")
    if template.content_hash != _template_hash(template):
        raise AuditTemplateError("published template content hash does not match its governed content")
    completed_by = completed_by.strip()
    if not completed_by:
        raise AuditTemplateError("completed_by is required")

    known = {question.question_id for question in template.questions}
    unknown = set(answers) - known
    if unknown:
        raise AuditTemplateError(f"answers contain unknown question ids: {sorted(unknown)}")

    visible_ids: list[str] = []
    awarded = 0
    possible = 0
    observed_answers: dict[str, Any] = {}

    for question in template.questions:
        visible = all(condition.matches(observed_answers) for condition in question.show_when)
        if not visible:
            if question.question_id in answers:
                raise AuditTemplateError(
                    f"hidden question {question.question_id} cannot receive an answer"
                )
            continue

        visible_ids.append(question.question_id)
        if question.question_id not in answers:
            if question.required:
                raise AuditTemplateError(f"required visible question {question.question_id} is missing")
            continue

        answer = answers[question.question_id]
        observed_answers[question.question_id] = answer
        if question.max_points:
            awarded += question.score_for(answer)
            possible += question.max_points

    percent = (
        (Decimal(awarded) * Decimal("100") / Decimal(possible)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if possible
        else Decimal("0.00")
    )
    completed_at = _utc(completed_at or datetime.now(UTC))
    run_id = audit_run_id or uuid4()
    frozen_answers = tuple(
        (question_id, answers[question_id])
        for question_id in visible_ids
        if question_id in answers
    )
    snapshot_payload = {
        "audit_run_id": str(run_id),
        "tenant_id": template.tenant_id,
        "template_key": template.template_key,
        "template_revision": template.revision,
        "template_hash": template.content_hash,
        "answers": list(frozen_answers),
        "visible_question_ids": visible_ids,
        "score_awarded": awarded,
        "score_possible": possible,
        "score_percent": str(percent),
        "completed_by": completed_by,
        "completed_at": completed_at.isoformat(),
    }
    return AuditRunSnapshot(
        audit_run_id=run_id,
        tenant_id=template.tenant_id,
        template_key=template.template_key,
        template_revision=template.revision,
        template_hash=template.content_hash,
        answers=frozen_answers,
        visible_question_ids=tuple(visible_ids),
        score_awarded=awarded,
        score_possible=possible,
        score_percent=percent,
        completed_by=completed_by,
        completed_at=completed_at,
        snapshot_hash=_sha(snapshot_payload),
    )


def _validate_questions(questions: tuple[AuditQuestion, ...]) -> None:
    if not questions:
        raise AuditTemplateError("template must contain at least one question")
    seen: set[str] = set()
    for question in questions:
        question_id = question.question_id.strip()
        if not question_id or question_id in seen:
            raise AuditTemplateError("question ids must be non-empty and unique")
        if not question.prompt_key.strip():
            raise AuditTemplateError(f"question {question_id} requires a prompt_key")
        if question.max_points < 0:
            raise AuditTemplateError(f"question {question_id} max_points cannot be negative")
        scoring = dict(question.scoring)
        if len(scoring) != len(question.scoring):
            raise AuditTemplateError(f"question {question_id} has duplicate scoring keys")
        if question.max_points == 0 and scoring:
            raise AuditTemplateError(f"informational question {question_id} cannot define scoring")
        if question.max_points > 0:
            if not scoring:
                raise AuditTemplateError(f"scored question {question_id} requires a scoring map")
            if any(points < 0 or points > question.max_points for points in scoring.values()):
                raise AuditTemplateError(
                    f"question {question_id} scoring must stay within 0..max_points"
                )
        for condition in question.show_when:
            if condition.question_id not in seen:
                raise AuditTemplateError(
                    f"question {question_id} branch condition must reference an earlier question"
                )
            if condition.operator in (BranchOperator.IN, BranchOperator.NOT_IN) and not isinstance(
                condition.expected, (tuple, list, set, frozenset)
            ):
                raise AuditTemplateError(
                    f"{condition.operator.value} branch condition requires a collection"
                )
        seen.add(question_id)


def _template_hash(template: AuditTemplateRevision) -> str:
    payload = {
        "tenant_id": template.tenant_id,
        "template_key": template.template_key,
        "revision": template.revision,
        "questions": [_question_payload(question) for question in template.questions],
    }
    return _sha(payload)


def _question_payload(question: AuditQuestion) -> dict[str, Any]:
    return {
        "question_id": question.question_id,
        "prompt_key": question.prompt_key,
        "max_points": question.max_points,
        "scoring": list(question.scoring),
        "required": question.required,
        "show_when": [
            {
                "question_id": condition.question_id,
                "operator": condition.operator.value,
                "expected": _json_safe(condition.expected),
            }
            for condition in question.show_when
        ],
    }


def _answer_key(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return value


def _sha(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise AuditTemplateError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
