"""Bounded parallel research frontier for Jarvis Autonomous Investigator.

The adaptive epistemic controller chooses what is worth learning next. This
module turns its candidate probes into a small parallel research wave so deep
research can gain breadth without creating an unbounded agent swarm.

It is planning-only: it never browses, calls a provider, promotes external
evidence to Company World truth, grants execution authority, or changes model
weights/business policy.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .adaptive_epistemic_control import (
    AdaptiveEpistemicDirective,
    EpistemicMoveKind,
    EpistemicProbe,
    EpistemicStrategy,
)
from .autonomous_investigator import AutonomousInvestigationReport

RESEARCH_FRONTIER_CONTRACT = "eay-research-frontier-v1"


class ResearchFrontierDecision(str, Enum):
    DISPATCH_BOUNDED_WAVE = "dispatch_bounded_wave"
    RETURN_TO_SEQUENTIAL_CONTROL = "return_to_sequential_control"
    HOLD_BUDGET_EXHAUSTED = "hold_budget_exhausted"
    HOLD_NO_NOVEL_PROBE = "hold_no_novel_probe"


class ResearchFrontierPolicy(BaseModel):
    maximum_depth: int = Field(default=4, ge=1, le=12)
    maximum_parallel_probes: int = Field(default=6, ge=1, le=24)
    maximum_total_probes: int = Field(default=24, ge=1, le=128)
    minimum_expected_information_gain: float = Field(default=0.16, ge=0.0, le=1.0)
    maximum_same_strategy_per_wave: int = Field(default=2, ge=1, le=8)
    require_leader_falsification: bool = True
    prefer_independent_corroboration: bool = True
    prefer_contradiction_lane: bool = True

    @model_validator(mode="after")
    def bounded(self) -> "ResearchFrontierPolicy":
        if self.maximum_parallel_probes > self.maximum_total_probes:
            raise ValueError("research_frontier_parallel_budget_exceeds_total")
        return self


class ResearchFrontierWave(BaseModel):
    contract: str = RESEARCH_FRONTIER_CONTRACT
    problem_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    directive_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    depth: int = Field(ge=0)
    decision: ResearchFrontierDecision
    leading_hypothesis_id: str | None = None
    probes: tuple[EpistemicProbe, ...] = ()
    scheduled_probe_count_before: int = Field(ge=0)
    scheduled_probe_count_after: int = Field(ge=0)
    strategy_count: int = Field(ge=0)
    expected_information_gain_sum: float = Field(ge=0.0)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    blockers: tuple[str, ...] = ()
    read_only: bool = True
    automatic_execution_allowed: bool = False
    direct_provider_call_allowed: bool = False
    execution_authority_granted: bool = False
    production_truth_promoted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integral_and_non_authoritative(self) -> "ResearchFrontierWave":
        if not self.read_only:
            raise ValueError("research_frontier_must_be_read_only")
        if any(
            (
                self.automatic_execution_allowed,
                self.direct_provider_call_allowed,
                self.execution_authority_granted,
                self.production_truth_promoted,
            )
        ):
            raise ValueError("research_frontier_never_grants_authority")
        ids = tuple(item.probe_id for item in self.probes)
        if len(ids) != len(set(ids)):
            raise ValueError("research_frontier_duplicate_probe")
        if self.scheduled_probe_count_after != (
            self.scheduled_probe_count_before + len(self.probes)
        ):
            raise ValueError("research_frontier_probe_count_mismatch")
        dispatch = self.decision is ResearchFrontierDecision.DISPATCH_BOUNDED_WAVE
        if dispatch != bool(self.probes):
            raise ValueError("research_frontier_dispatch_probe_mismatch")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("research_frontier_fingerprint_mismatch")
        return self


def plan_research_frontier_wave(
    *,
    directive: AdaptiveEpistemicDirective,
    report: AutonomousInvestigationReport,
    depth: int,
    prior_probe_ids: tuple[str, ...] = (),
    policy: ResearchFrontierPolicy | None = None,
) -> ResearchFrontierWave:
    """Compose one bounded, diverse read-only research wave."""

    rules = policy or ResearchFrontierPolicy()
    _validate_scope(directive, report)
    if depth < 0:
        raise ValueError("research_frontier_depth_negative")
    if len(prior_probe_ids) != len(set(prior_probe_ids)):
        raise ValueError("research_frontier_prior_probe_ids_not_unique")

    if directive.move_kind in {
        EpistemicMoveKind.STOP_EVIDENCE_SUFFICIENT,
        EpistemicMoveKind.EXPAND_HYPOTHESIS_SPACE,
    }:
        return _wave(
            directive=directive,
            report=report,
            depth=depth,
            decision=ResearchFrontierDecision.RETURN_TO_SEQUENTIAL_CONTROL,
            prior_count=len(prior_probe_ids),
            reasons=("research_frontier_sequential_control_required",),
        )
    if directive.move_kind is EpistemicMoveKind.HOLD_LIMIT_REACHED:
        return _wave(
            directive=directive,
            report=report,
            depth=depth,
            decision=ResearchFrontierDecision.HOLD_BUDGET_EXHAUSTED,
            prior_count=len(prior_probe_ids),
            reasons=("research_frontier_upstream_round_budget_exhausted",),
            blockers=directive.blockers,
        )
    if depth >= rules.maximum_depth or len(prior_probe_ids) >= rules.maximum_total_probes:
        return _wave(
            directive=directive,
            report=report,
            depth=depth,
            decision=ResearchFrontierDecision.HOLD_BUDGET_EXHAUSTED,
            prior_count=len(prior_probe_ids),
            reasons=("research_frontier_budget_exhausted",),
            blockers=("research_frontier_requires_fresh_sequential_assessment",),
        )

    candidates = _dedupe_candidates(directive)
    prior = set(prior_probe_ids)
    candidates = tuple(item for item in candidates if item.probe_id not in prior)
    if not candidates:
        return _wave(
            directive=directive,
            report=report,
            depth=depth,
            decision=ResearchFrontierDecision.HOLD_NO_NOVEL_PROBE,
            prior_count=len(prior_probe_ids),
            reasons=("research_frontier_no_novel_probe",),
            blockers=("research_frontier_requires_new_epistemic_candidates",),
        )

    leader_id = report.ranking.leading_hypothesis_id if report.ranking else None
    remaining_budget = rules.maximum_total_probes - len(prior_probe_ids)
    wave_limit = min(rules.maximum_parallel_probes, remaining_budget)
    selected = _select_diverse_wave(
        candidates=candidates,
        leader_id=leader_id,
        limit=wave_limit,
        rules=rules,
    )
    if not selected:
        return _wave(
            directive=directive,
            report=report,
            depth=depth,
            decision=ResearchFrontierDecision.HOLD_NO_NOVEL_PROBE,
            prior_count=len(prior_probe_ids),
            reasons=("research_frontier_information_gain_below_floor",),
            blockers=("research_frontier_requires_new_epistemic_candidates",),
        )

    reasons = ["research_frontier_bounded_parallel_wave_planned"]
    strategies = {item.strategy for item in selected}
    if any(
        item.strategy is EpistemicStrategy.FALSIFICATION
        and item.hypothesis_id == leader_id
        for item in selected
    ):
        reasons.append("research_frontier_leader_falsification_included")
    if EpistemicStrategy.CONTRADICTION_FIRST in strategies:
        reasons.append("research_frontier_contradiction_lane_included")
    if EpistemicStrategy.INDEPENDENT_CORROBORATION in strategies:
        reasons.append("research_frontier_independent_corroboration_included")
    if len(strategies) >= 3:
        reasons.append("research_frontier_strategy_diversity_achieved")

    return _wave(
        directive=directive,
        report=report,
        depth=depth,
        decision=ResearchFrontierDecision.DISPATCH_BOUNDED_WAVE,
        prior_count=len(prior_probe_ids),
        probes=selected,
        reasons=tuple(reasons),
        blockers=directive.blockers,
    )


def _dedupe_candidates(
    directive: AdaptiveEpistemicDirective,
) -> tuple[EpistemicProbe, ...]:
    values = (
        directive.candidate_probes
        if directive.candidate_probes
        else ((directive.selected_probe,) if directive.selected_probe else ())
    )
    by_id: dict[str, EpistemicProbe] = {}
    for item in values:
        existing = by_id.get(item.probe_id)
        if existing is not None and existing != item:
            raise ValueError("research_frontier_probe_identity_conflict")
        by_id[item.probe_id] = item
    return tuple(by_id[key] for key in sorted(by_id))


def _select_diverse_wave(
    *,
    candidates: tuple[EpistemicProbe, ...],
    leader_id: str | None,
    limit: int,
    rules: ResearchFrontierPolicy,
) -> tuple[EpistemicProbe, ...]:
    eligible = tuple(
        item
        for item in candidates
        if item.expected_information_gain >= rules.minimum_expected_information_gain
        or (
            rules.require_leader_falsification
            and item.strategy is EpistemicStrategy.FALSIFICATION
            and item.hypothesis_id == leader_id
        )
    )
    if not eligible or limit <= 0:
        return ()

    priority: list[EpistemicProbe] = []
    mandatory = next(
        (
            item
            for item in eligible
            if rules.require_leader_falsification
            and item.strategy is EpistemicStrategy.FALSIFICATION
            and item.hypothesis_id == leader_id
        ),
        None,
    )
    if mandatory is not None:
        priority.append(mandatory)

    requested_strategies: list[EpistemicStrategy] = []
    if rules.prefer_contradiction_lane:
        requested_strategies.append(EpistemicStrategy.CONTRADICTION_FIRST)
    if rules.prefer_independent_corroboration:
        requested_strategies.append(EpistemicStrategy.INDEPENDENT_CORROBORATION)
    requested_strategies.extend(
        (
            EpistemicStrategy.PRIMARY_TRIANGULATION,
            EpistemicStrategy.TEMPORAL_REFRESH,
            EpistemicStrategy.QUANTITATIVE_VALIDATION,
            EpistemicStrategy.CROSS_DOMAIN_EXPANSION,
        )
    )
    for strategy in requested_strategies:
        best = _best_for_strategy(eligible, strategy, excluded=priority)
        if best is not None:
            priority.append(best)

    remaining = sorted(
        (item for item in eligible if item not in priority),
        key=lambda item: (-item.expected_information_gain, item.probe_id),
    )
    priority.extend(remaining)

    selected: list[EpistemicProbe] = []
    strategy_counts: dict[EpistemicStrategy, int] = {}
    for item in priority:
        if len(selected) >= limit:
            break
        count = strategy_counts.get(item.strategy, 0)
        if count >= rules.maximum_same_strategy_per_wave:
            continue
        selected.append(item)
        strategy_counts[item.strategy] = count + 1
    return tuple(selected)


def _best_for_strategy(
    candidates: tuple[EpistemicProbe, ...],
    strategy: EpistemicStrategy,
    *,
    excluded: list[EpistemicProbe],
) -> EpistemicProbe | None:
    values = [
        item
        for item in candidates
        if item.strategy is strategy and item not in excluded
    ]
    if not values:
        return None
    return min(values, key=lambda item: (-item.expected_information_gain, item.probe_id))


def _validate_scope(
    directive: AdaptiveEpistemicDirective,
    report: AutonomousInvestigationReport,
) -> None:
    if directive.problem_id != report.problem_id:
        raise ValueError("research_frontier_problem_mismatch")
    if directive.tenant_id != report.tenant_id:
        raise ValueError("research_frontier_tenant_mismatch")
    if directive.company_id != report.company_id:
        raise ValueError("research_frontier_company_mismatch")


def _wave(
    *,
    directive: AdaptiveEpistemicDirective,
    report: AutonomousInvestigationReport,
    depth: int,
    decision: ResearchFrontierDecision,
    prior_count: int,
    reasons: tuple[str, ...],
    probes: tuple[EpistemicProbe, ...] = (),
    blockers: tuple[str, ...] = (),
) -> ResearchFrontierWave:
    strategies = {item.strategy for item in probes}
    draft = {
        "contract": RESEARCH_FRONTIER_CONTRACT,
        "problem_id": directive.problem_id,
        "tenant_id": directive.tenant_id,
        "company_id": directive.company_id,
        "directive_fingerprint": directive.fingerprint,
        "report_fingerprint": report.fingerprint,
        "depth": depth,
        "decision": decision.value,
        "leading_hypothesis_id": (
            report.ranking.leading_hypothesis_id if report.ranking else None
        ),
        "probes": [item.model_dump(mode="json") for item in probes],
        "scheduled_probe_count_before": prior_count,
        "scheduled_probe_count_after": prior_count + len(probes),
        "strategy_count": len(strategies),
        "expected_information_gain_sum": round(
            sum(item.expected_information_gain for item in probes),
            6,
        ),
        "reason_codes": list(dict.fromkeys(reasons)),
        "blockers": list(dict.fromkeys(blockers)),
        "read_only": True,
        "automatic_execution_allowed": False,
        "direct_provider_call_allowed": False,
        "execution_authority_granted": False,
        "production_truth_promoted": False,
    }
    return ResearchFrontierWave.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
