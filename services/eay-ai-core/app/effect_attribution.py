"""Attribute observed business-state changes to candidate requests conservatively.

Timing alone is not enough to decide which POST caused a stock, roster or other
business mutation.  This module ranks already-observed candidates using state
field overlap, successful response evidence and independent read-back support,
while penalizing telemetry/audit traffic.  It never calls correlation causal
proof and never authorizes direct API execution; replay/equivalence validation
is a separate promotion gate.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

EFFECT_ATTRIBUTION_CONTRACT = "eay-effect-attribution-v1"


class EffectDisposition(str, Enum):
    INSUFFICIENT = "insufficient"
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"


class StateTransitionObservation(BaseModel):
    transition_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    entity_ref: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    before_value: Any
    after_value: Any
    verifier_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def transition_must_change_state(self) -> "StateTransitionObservation":
        if self.before_value == self.after_value:
            raise ValueError("effect_transition_requires_state_change")
        return self


class EffectRequestCandidate(BaseModel):
    request_ref: str = Field(min_length=1)
    method: str = Field(min_length=3, max_length=12)
    operation_ref: str = Field(min_length=1)
    status_code: int = Field(ge=100, le=599)
    tenant_id: str = Field(min_length=1)
    request_field_names: tuple[str, ...] = ()
    response_field_names: tuple[str, ...] = ()
    state_field_hints: tuple[str, ...] = ()
    independent_readback_matches: bool = False
    transaction_reference_observed: bool = False
    telemetry_like: bool = False
    audit_like: bool = False
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def normalize_method(self) -> "EffectRequestCandidate":
        self.method = self.method.upper()
        if not self.evidence_refs:
            raise ValueError("effect_request_candidate_requires_evidence")
        return self


class EffectCandidateScore(BaseModel):
    request_ref: str
    score: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...]


class EffectAttributionDecision(BaseModel):
    contract: str = EFFECT_ATTRIBUTION_CONTRACT
    transition_id: str
    disposition: EffectDisposition
    selected_request_ref: str | None = None
    ranked_candidates: tuple[EffectCandidateScore, ...] = ()
    causal_proof: bool = False
    replay_equivalence_required: bool = True
    direct_api_execution_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def preserve_truth_boundary(self) -> "EffectAttributionDecision":
        if self.causal_proof:
            raise ValueError("effect_attribution_cannot_claim_causal_proof")
        if self.direct_api_execution_allowed:
            raise ValueError("effect_attribution_never_authorizes_direct_execution")
        if self.disposition is EffectDisposition.CANDIDATE and not self.selected_request_ref:
            raise ValueError("effect_candidate_requires_selected_request")
        return self


def _score(
    transition: StateTransitionObservation,
    candidate: EffectRequestCandidate,
) -> EffectCandidateScore | None:
    if candidate.tenant_id != transition.tenant_id:
        return None

    method = candidate.method.upper()
    score = 0.10
    reasons: list[str] = ["tenant_match"]

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        score += 0.20
        reasons.append("write_semantics")
    else:
        score -= 0.10
        reasons.append("non_write_semantics")

    if 200 <= candidate.status_code < 400:
        score += 0.12
        reasons.append("successful_response")

    normalized_field = transition.field_name.casefold()
    request_names = {name.casefold() for name in candidate.request_field_names}
    response_names = {name.casefold() for name in candidate.response_field_names}
    hints = {name.casefold() for name in candidate.state_field_hints}

    if normalized_field in hints:
        score += 0.24
        reasons.append("explicit_state_field_hint")
    elif any(normalized_field in name or name in normalized_field for name in request_names | response_names):
        score += 0.15
        reasons.append("state_field_schema_overlap")

    if candidate.independent_readback_matches:
        score += 0.25
        reasons.append("independent_readback_matches")
    if candidate.transaction_reference_observed:
        score += 0.10
        reasons.append("transaction_reference_observed")

    if candidate.telemetry_like:
        score -= 0.30
        reasons.append("telemetry_penalty")
    if candidate.audit_like:
        score -= 0.20
        reasons.append("audit_side_channel_penalty")

    return EffectCandidateScore(
        request_ref=candidate.request_ref,
        score=max(0.0, min(score, 1.0)),
        reasons=tuple(reasons),
    )


def attribute_effect(
    *,
    transition: StateTransitionObservation,
    candidates: list[EffectRequestCandidate],
    minimum_score: float = 0.65,
    ambiguity_margin: float = 0.10,
) -> EffectAttributionDecision:
    if not 0.0 <= minimum_score <= 1.0:
        raise ValueError("effect_minimum_score_out_of_range")
    if not 0.0 <= ambiguity_margin <= 1.0:
        raise ValueError("effect_ambiguity_margin_out_of_range")

    ranked = [score for candidate in candidates if (score := _score(transition, candidate)) is not None]
    ranked.sort(key=lambda item: (-item.score, item.request_ref))
    if not ranked:
        return EffectAttributionDecision(
            transition_id=transition.transition_id,
            disposition=EffectDisposition.INSUFFICIENT,
            blockers=("effect_no_tenant_scoped_request_candidates",),
        )

    best = ranked[0]
    if best.score < minimum_score:
        return EffectAttributionDecision(
            transition_id=transition.transition_id,
            disposition=EffectDisposition.INSUFFICIENT,
            ranked_candidates=tuple(ranked[:5]),
            blockers=("effect_attribution_below_threshold",),
        )

    if len(ranked) > 1 and (best.score - ranked[1].score) < ambiguity_margin:
        return EffectAttributionDecision(
            transition_id=transition.transition_id,
            disposition=EffectDisposition.AMBIGUOUS,
            ranked_candidates=tuple(ranked[:5]),
            blockers=("effect_attribution_ambiguous",),
        )

    return EffectAttributionDecision(
        transition_id=transition.transition_id,
        disposition=EffectDisposition.CANDIDATE,
        selected_request_ref=best.request_ref,
        ranked_candidates=tuple(ranked[:5]),
        blockers=("effect_replay_equivalence_not_yet_verified",),
    )
