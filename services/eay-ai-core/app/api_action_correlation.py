"""Correlate an authorized UI action with the network traffic it caused.

This is the bridge that lets Jarvis learn an undocumented portal API from one
legitimate workflow demonstration. It uses timing, application, tenant scope,
HTTP mutation semantics and browser resource type. It fails closed on weak or
ambiguous matches instead of binding an arbitrary POST request to the user's
intent.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .api_discovery_intelligence import ObservedHttpExchange, OperationKind, _operation_kind

API_ACTION_CORRELATION_CONTRACT = "eay-api-action-correlation-v1"


class UiActionKind(str, Enum):
    READ = "read"
    WRITE = "write"
    UNKNOWN = "unknown"


class UiActionObservation(BaseModel):
    contract: str = API_ACTION_CORRELATION_CONTRACT
    action_ref: str = Field(min_length=3)
    application_id: str = Field(min_length=1)
    started_at_ms: int = Field(ge=0)
    completed_at_ms: int = Field(ge=0)
    action_kind: UiActionKind = UiActionKind.UNKNOWN
    tenant_scope_ref: str | None = None
    managed_auth_context_ref: str | None = None

    @model_validator(mode="after")
    def valid_time_window(self) -> "UiActionObservation":
        if self.completed_at_ms < self.started_at_ms:
            raise ValueError("ui_action_completion_precedes_start")
        return self


class TimedExchange(BaseModel):
    exchange: ObservedHttpExchange
    observed_at_ms: int = Field(ge=0)


class CorrelationCandidate(BaseModel):
    exchange_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    score: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...] = ()
    exchange: ObservedHttpExchange


class ActionCorrelationDecision(BaseModel):
    contract: str = API_ACTION_CORRELATION_CONTRACT
    action_ref: str
    correlated: bool = False
    ambiguous: bool = False
    best_score: float = Field(ge=0.0, le=1.0)
    selected_exchange: ObservedHttpExchange | None = None
    alternatives: tuple[CorrelationCandidate, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def correlation_cannot_be_ambiguous(self) -> "ActionCorrelationDecision":
        if self.correlated and self.ambiguous:
            raise ValueError("api_action_correlation_cannot_be_ambiguous")
        if self.correlated and self.selected_exchange is None:
            raise ValueError("api_action_correlation_requires_selected_exchange")
        return self


def _exchange_ref(exchange: ObservedHttpExchange) -> str:
    canonical = json.dumps(
        {
            "application_id": exchange.application_id,
            "method": exchange.method,
            "url": exchange.url,
            "status": exchange.status_code,
            "request_fp": exchange.request_body_fingerprint,
            "response_fp": exchange.response_body_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _score(action: UiActionObservation, timed: TimedExchange, *, post_action_window_ms: int) -> CorrelationCandidate | None:
    exchange = timed.exchange
    if exchange.application_id != action.application_id:
        return None
    if timed.observed_at_ms < max(0, action.started_at_ms - 250):
        return None
    if timed.observed_at_ms > action.completed_at_ms + post_action_window_ms:
        return None

    score = 0.30
    reasons = ["same_application", "within_action_time_window"]

    operation_kind = _operation_kind(exchange.method)
    if action.action_kind is UiActionKind.WRITE and operation_kind is OperationKind.WRITE:
        score += 0.25
        reasons.append("write_semantics_match")
    elif action.action_kind is UiActionKind.READ and operation_kind is OperationKind.READ:
        score += 0.20
        reasons.append("read_semantics_match")
    elif action.action_kind is not UiActionKind.UNKNOWN:
        score -= 0.15
        reasons.append("operation_semantics_mismatch")

    if exchange.resource_type and exchange.resource_type.casefold() in {"xhr", "fetch"}:
        score += 0.15
        reasons.append("xhr_or_fetch")
    if 200 <= exchange.status_code < 400:
        score += 0.10
        reasons.append("successful_response")

    if action.tenant_scope_ref:
        if exchange.tenant_scope_ref == action.tenant_scope_ref:
            score += 0.10
            reasons.append("tenant_scope_match")
        elif exchange.tenant_scope_ref:
            score -= 0.25
            reasons.append("tenant_scope_mismatch")

    if action.managed_auth_context_ref:
        if exchange.auth_context_ref == action.managed_auth_context_ref:
            score += 0.10
            reasons.append("auth_context_match")
        elif exchange.auth_context_ref:
            score -= 0.20
            reasons.append("auth_context_mismatch")

    # Requests closest to the completion/click point receive a bounded tie-break.
    distance = abs(timed.observed_at_ms - action.completed_at_ms)
    proximity_bonus = max(0.0, 0.10 * (1.0 - min(distance, post_action_window_ms) / post_action_window_ms))
    if proximity_bonus:
        score += proximity_bonus
        reasons.append("temporal_proximity")

    return CorrelationCandidate(
        exchange_ref=_exchange_ref(exchange),
        score=max(0.0, min(score, 1.0)),
        reasons=tuple(reasons),
        exchange=exchange,
    )


def correlate_ui_action(
    action: UiActionObservation,
    exchanges: list[TimedExchange],
    *,
    minimum_score: float = 0.70,
    ambiguity_margin: float = 0.08,
    post_action_window_ms: int = 5000,
) -> ActionCorrelationDecision:
    if not 0.0 <= minimum_score <= 1.0:
        raise ValueError("api_action_minimum_score_out_of_range")
    if not 0.0 <= ambiguity_margin <= 1.0:
        raise ValueError("api_action_ambiguity_margin_out_of_range")
    if post_action_window_ms <= 0:
        raise ValueError("api_action_post_window_must_be_positive")

    ranked = [
        candidate
        for timed in exchanges
        if (candidate := _score(action, timed, post_action_window_ms=post_action_window_ms)) is not None
    ]
    ranked.sort(key=lambda item: (-item.score, item.exchange_ref))
    if not ranked:
        return ActionCorrelationDecision(
            action_ref=action.action_ref,
            blockers=("api_action_no_network_candidate_in_window",),
        )

    best = ranked[0]
    if best.score < minimum_score:
        return ActionCorrelationDecision(
            action_ref=action.action_ref,
            best_score=best.score,
            alternatives=tuple(ranked[:5]),
            blockers=("api_action_correlation_below_threshold",),
        )

    ambiguous = len(ranked) > 1 and (best.score - ranked[1].score) < ambiguity_margin
    if ambiguous:
        return ActionCorrelationDecision(
            action_ref=action.action_ref,
            best_score=best.score,
            ambiguous=True,
            alternatives=tuple(ranked[:5]),
            blockers=("api_action_correlation_ambiguous",),
        )

    selected = best.exchange.model_copy(
        update={
            "user_action_ref": action.action_ref,
            "tenant_scope_ref": action.tenant_scope_ref or best.exchange.tenant_scope_ref,
            "auth_context_ref": action.managed_auth_context_ref or best.exchange.auth_context_ref,
        }
    )
    return ActionCorrelationDecision(
        action_ref=action.action_ref,
        correlated=True,
        best_score=best.score,
        selected_exchange=selected,
        alternatives=tuple(ranked[:5]),
    )
