"""Deterministic, observable claim/evidence trace for grounded Jarvis answers.

The trace is deliberately not chain-of-thought. It serializes only the public
structured answer, retrieved evidence identifiers/authority, deterministic
quality gaps, and verifier outcomes so operators can inspect why a conclusion
was allowed, capped, revised, or escalated.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

DECISION_TRACE_CONTRACT = "grounded-decision-trace-v1"
_LAYER_ORDER = ("legal", "company", "standard", "operational")
_ANSWER_FIELD = {
    "legal": "legal",
    "company": "company",
    "standard": "standards",
    "operational": "operational",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _iso(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    return text or None


def _model_value(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TraceEvidence(BaseModel):
    id: str
    layer: str
    authority_level: str
    score: float = 0.0
    effective_from: str | None = None
    effective_to: str | None = None


class TraceClaim(BaseModel):
    layer: str
    status: str
    summary: str
    citation_ids: list[str] = Field(default_factory=list)
    valid_citation_ids: list[str] = Field(default_factory=list)
    invalid_citation_ids: list[str] = Field(default_factory=list)
    support_state: Literal[
        "supported",
        "partially_supported",
        "unsupported",
        "no_claim",
    ]


class GroundedDecisionTrace(BaseModel):
    contract: str = DECISION_TRACE_CONTRACT
    question_fingerprint: str
    as_of: str
    active_layers: list[str] = Field(default_factory=list)
    required_layers: list[str] = Field(default_factory=list)
    missing_required_layers: list[str] = Field(default_factory=list)
    evidence_inventory: list[TraceEvidence] = Field(default_factory=list)
    claims: list[TraceClaim] = Field(default_factory=list)
    recommendation_basis_evidence_ids: list[str] = Field(default_factory=list)
    recommendation_basis_state: Literal[
        "supported_findings_present",
        "no_supported_findings",
    ] = "no_supported_findings"
    critic_verdict: str | None = None
    critic_issue_codes: list[str] = Field(default_factory=list)
    critic_revision_applied: bool = False
    final_confidence: float
    requires_human_review: bool
    evidence_sufficient: bool | None = None
    production_authority: bool = False
    trace_fingerprint: str


def _question_fingerprint(request: Any) -> str:
    payload = {
        "message": _text(_model_value(request, "message")),
        "as_of": _iso(_model_value(request, "as_of")),
        "layers": sorted(str(item) for item in (_model_value(request, "layers", []) or [])),
    }
    return _fingerprint(payload)


def _evidence_inventory(evidence: list[Any]) -> list[TraceEvidence]:
    rows = []
    for item in evidence:
        evidence_id = _text(_model_value(item, "id"))
        if not evidence_id:
            continue
        rows.append(
            TraceEvidence(
                id=evidence_id,
                layer=_text(_model_value(item, "layer")),
                authority_level=_text(_model_value(item, "authority_level")),
                score=float(_model_value(item, "score", 0.0) or 0.0),
                effective_from=_iso(_model_value(item, "effective_from")),
                effective_to=_iso(_model_value(item, "effective_to")),
            )
        )
    rows.sort(key=lambda row: (row.layer, row.id))
    return rows


def _claims(answer: Any, valid_ids: set[str]) -> list[TraceClaim]:
    result = []
    for layer in _LAYER_ORDER:
        finding = _model_value(answer, _ANSWER_FIELD[layer])
        status = _text(_model_value(finding, "status"))
        summary = _text(_model_value(finding, "summary"))
        citation_ids = [
            _text(item)
            for item in (_model_value(finding, "citations", []) or [])
            if _text(item)
        ]
        valid = [item for item in citation_ids if item in valid_ids]
        invalid = [item for item in citation_ids if item not in valid_ids]
        normalized_status = status.casefold().replace("_", " ").strip()
        no_claim = normalized_status in {
            "",
            "insufficient",
            "not applicable",
            "not requested",
            "none",
        } and not summary
        if no_claim:
            support_state = "no_claim"
        elif valid and not invalid:
            support_state = "supported"
        elif valid:
            support_state = "partially_supported"
        else:
            support_state = "unsupported"
        result.append(
            TraceClaim(
                layer=layer,
                status=status,
                summary=summary,
                citation_ids=citation_ids,
                valid_citation_ids=valid,
                invalid_citation_ids=invalid,
                support_state=support_state,
            )
        )
    return result


def build_grounded_decision_trace(
    *,
    request: Any,
    answer: Any,
    evidence: list[Any],
    evidence_plan: Any | None = None,
    decision_quality: Any | None = None,
    critic: Any | None = None,
) -> GroundedDecisionTrace:
    inventory = _evidence_inventory(evidence)
    valid_ids = {row.id for row in inventory}
    claims = _claims(answer, valid_ids)

    active_layers = [
        str(item)
        for item in (_model_value(evidence_plan, "active_layers", []) or [])
    ]
    required_layers = [
        str(item)
        for item in (
            _model_value(decision_quality, "required_layers", None)
            or _model_value(evidence_plan, "inferred_required_layers", [])
            or []
        )
    ]
    missing_layers = [
        str(item)
        for item in (
            _model_value(decision_quality, "missing_required_layers", []) or []
        )
    ]

    recommendation_basis = sorted(
        {
            citation
            for claim in claims
            if claim.support_state in {"supported", "partially_supported"}
            for citation in claim.valid_citation_ids
        }
    )
    critic_issues = [
        _text(_model_value(issue, "code"))
        for issue in (_model_value(critic, "issues", []) or [])
        if _text(_model_value(issue, "code"))
    ]

    fingerprint_payload = {
        "contract": DECISION_TRACE_CONTRACT,
        "question_fingerprint": _question_fingerprint(request),
        "as_of": _iso(_model_value(request, "as_of")) or "",
        "active_layers": active_layers,
        "required_layers": required_layers,
        "missing_required_layers": missing_layers,
        "evidence_inventory": [row.model_dump() for row in inventory],
        "claims": [row.model_dump() for row in claims],
        "recommendation_basis_evidence_ids": recommendation_basis,
        "critic_verdict": _text(_model_value(critic, "verdict")) or None,
        "critic_issue_codes": critic_issues,
        "critic_revision_applied": bool(_model_value(critic, "revision_applied", False)),
        "final_confidence": float(_model_value(answer, "confidence", 0.0) or 0.0),
        "requires_human_review": bool(_model_value(answer, "requires_human_review", False)),
        "evidence_sufficient": _model_value(decision_quality, "evidence_sufficient", None),
        "production_authority": False,
    }
    return GroundedDecisionTrace(
        **fingerprint_payload,
        recommendation_basis_state=(
            "supported_findings_present"
            if recommendation_basis
            else "no_supported_findings"
        ),
        trace_fingerprint=_fingerprint(fingerprint_payload),
    )
