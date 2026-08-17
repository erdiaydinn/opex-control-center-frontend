"""Adaptive verifier/critic for grounded Jarvis answers.

The critic receives only observable inputs: user question, retrieved evidence,
structured answer and deterministic decision-quality report. It must not expose
or request private chain-of-thought. Its output is a compact verdict, issue codes
and revision instructions that can be audited and regression-tested.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

CRITIC_CONTRACT = "grounded-verifier-critic-v1"

CriticVerdict = Literal["PASS", "REVISE", "REJECT", "NOT_RUN", "UNAVAILABLE"]
CriticIssueCode = Literal[
    "unsupported_claim",
    "citation_gap",
    "evidence_conflict",
    "missing_required_layer",
    "temporal_mismatch",
    "overconfident",
    "high_risk_action",
    "ambiguous_recommendation",
    "layer_collapse",
    "legal_overclaim",
]

_COMPLEX_TERMS = {
    "why",
    "neden",
    "root cause",
    "kök neden",
    "kok neden",
    "compare",
    "comparison",
    "karşılaştır",
    "karsilastir",
    "recommend",
    "recommendation",
    "öner",
    "oner",
    "decision",
    "karar",
    "optimize",
    "optimiz",
    "risk",
    "forecast",
    "tahmin",
    "scenario",
    "senaryo",
    "tradeoff",
    "trade-off",
}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.casefold().replace("ı", "i")).strip()


def critic_enabled() -> bool:
    raw = os.getenv("EAY_GROUNDED_CRITIC_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class GroundedCriticReport(BaseModel):
    contract: str = CRITIC_CONTRACT
    performed: bool = False
    verdict: CriticVerdict = "NOT_RUN"
    issue_codes: list[CriticIssueCode] = Field(default_factory=list)
    confidence_cap: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_human_review: bool = False
    revision_instructions: list[str] = Field(default_factory=list, max_length=8)
    revision_applied: bool = False
    revision_guard_passed: bool = False


CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "REVISE", "REJECT"],
        },
        "issue_codes": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "unsupported_claim",
                    "citation_gap",
                    "evidence_conflict",
                    "missing_required_layer",
                    "temporal_mismatch",
                    "overconfident",
                    "high_risk_action",
                    "ambiguous_recommendation",
                    "layer_collapse",
                    "legal_overclaim",
                ],
            },
            "maxItems": 8,
        },
        "confidence_cap": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "requires_human_review": {"type": "boolean"},
        "revision_instructions": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
    },
    "required": [
        "verdict",
        "issue_codes",
        "confidence_cap",
        "requires_human_review",
        "revision_instructions",
    ],
}

CRITIC_SYSTEM_PROMPT = """
You are EAY Jarvis Verifier, an evidence-bound answer critic.
You do not generate hidden reasoning or chain-of-thought.
Evaluate only the observable answer against the supplied evidence and authority layers.

Rules:
1. Output only JSON matching the schema.
2. Use PASS only when material claims are supported and cited appropriately.
3. Use REVISE when the evidence is sufficient but the answer wording, confidence,
   recommendation, layer separation or citations need correction.
4. Use REJECT when a material conclusion cannot be responsibly stated from the
   supplied evidence or a high-risk recommendation would exceed evidence/authority.
5. Never invent facts, citations, legal duties, company rules, thresholds or dates.
6. LEGAL, COMPANY, STANDARD and OPERATIONAL layers must remain distinct.
7. confidence_cap may only preserve or reduce confidence; never reward eloquence.
8. revision_instructions must be short, actionable observable corrections, never
   hidden reasoning traces.
""".strip()


def should_run_grounded_critic(
    request: Any,
    answer: Any,
    decision_quality: Any,
) -> bool:
    if not critic_enabled():
        return False
    if not bool(getattr(decision_quality, "evidence_sufficient", False)):
        return False

    required_layers = list(getattr(decision_quality, "required_layers", []) or [])
    if "legal" in required_layers or "company" in required_layers:
        return True
    if len(required_layers) >= 2:
        return True

    risk = _norm(getattr(answer, "risk", "unknown"))
    if risk in {"high", "critical"}:
        return True

    message = _norm(getattr(request, "message", ""))
    if any(_norm(term) in message for term in _COMPLEX_TERMS):
        return True

    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    return confidence >= 0.85


def is_high_assurance_critic(
    request: Any,
    answer: Any,
    decision_quality: Any,
) -> bool:
    required_layers = list(getattr(decision_quality, "required_layers", []) or [])
    if "legal" in required_layers or "company" in required_layers:
        return True
    risk = _norm(getattr(answer, "risk", "unknown"))
    if risk in {"high", "critical"}:
        return True
    message = _norm(getattr(request, "message", ""))
    return any(term in message for term in ("approve", "onay", "publish", "yayin", "yayın"))


def build_critic_prompt(
    *,
    request: Any,
    answer: Any,
    evidence_text: str,
    decision_quality: Any,
) -> str:
    answer_payload = (
        answer.model_dump(mode="json")
        if hasattr(answer, "model_dump")
        else dict(answer)
    )
    quality_payload = (
        decision_quality.model_dump(mode="json")
        if hasattr(decision_quality, "model_dump")
        else dict(decision_quality)
    )
    return f"""
USER QUESTION:
{getattr(request, 'message', '')}

AS_OF:
{getattr(request, 'as_of', 'unknown')}

RETRIEVED EVIDENCE:
{evidence_text}

CANDIDATE ANSWER JSON:
{json.dumps(answer_payload, ensure_ascii=False, sort_keys=True)}

DETERMINISTIC DECISION QUALITY JSON:
{json.dumps(quality_payload, ensure_ascii=False, sort_keys=True)}

Return only the verifier verdict. Do not reveal hidden reasoning.
""".strip()


def build_revision_prompt(
    *,
    request: Any,
    answer: Any,
    evidence_text: str,
    critic: GroundedCriticReport,
) -> str:
    answer_payload = answer.model_dump(mode="json")
    critic_payload = critic.model_dump(mode="json")
    return f"""
USER QUESTION:
{getattr(request, 'message', '')}

AS_OF:
{getattr(request, 'as_of', 'unknown')}

RETRIEVED EVIDENCE:
{evidence_text}

CURRENT ANSWER JSON:
{json.dumps(answer_payload, ensure_ascii=False, sort_keys=True)}

VERIFIER RESULT JSON:
{json.dumps(critic_payload, ensure_ascii=False, sort_keys=True)}

Revise the answer only to address the verifier instructions. Do not add evidence,
facts, citations, law, company rules, thresholds or dates that are not supplied.
Keep all evidence layers separate. Return only the normal answer JSON schema.
""".strip()


def normalize_critic_report(
    payload: dict[str, Any],
    *,
    current_confidence: float,
) -> GroundedCriticReport:
    report = GroundedCriticReport(performed=True, **payload)
    # A model verifier can never raise answer confidence.
    report.confidence_cap = min(
        max(0.0, float(report.confidence_cap)),
        max(0.0, float(current_confidence)),
    )
    if report.verdict == "PASS":
        # PASS with issue codes is internally inconsistent; fail closed to REVISE.
        if report.issue_codes:
            report.verdict = "REVISE"
    elif not report.issue_codes:
        report.issue_codes = ["ambiguous_recommendation"]
    if report.verdict == "REVISE" and not report.revision_instructions:
        report.requires_human_review = True
    if report.verdict == "REJECT":
        report.requires_human_review = True
        report.confidence_cap = min(report.confidence_cap, 0.50)
    return report


def unavailable_critic_report(
    *,
    current_confidence: float,
    high_assurance: bool,
) -> GroundedCriticReport:
    return GroundedCriticReport(
        performed=False,
        verdict="UNAVAILABLE",
        confidence_cap=min(current_confidence, 0.65 if high_assurance else 0.75),
        requires_human_review=high_assurance,
        revision_instructions=[],
    )


def apply_critic_constraints(answer: Any, report: GroundedCriticReport) -> None:
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    setattr(answer, "confidence", min(confidence, report.confidence_cap))
    if report.requires_human_review or report.verdict == "REJECT":
        setattr(answer, "requires_human_review", True)
