"""Master 56-60 release, pilot, activation, stabilization, and leadership authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class ReleaseState(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
    PILOT = "PILOT"
    PILOT_ACCEPTED = "PILOT_ACCEPTED"
    PRODUCTION_ACTIVE = "PRODUCTION_ACTIVE"
    STABILIZING = "STABILIZING"


REQUIRED_EXTERNAL = tuple(range(49, 56))
REQUIRED_SRE = tuple(range(45, 49))
PILOT_METRICS = (
    "error_budget",
    "task_success",
    "latency",
    "reconciliation",
    "support_cases",
    "device_issues",
    "user_feedback",
    "rollback_criteria",
)
PROD_SIGNOFFS = ("security", "dr", "identity", "real_data", "module_owner")


@dataclass(frozen=True)
class ReleaseTruth:
    repository_green: bool
    repository_evidence_ref: str = ""
    sre_items: Mapping[int, bool] = field(default_factory=dict)
    sre_evidence_refs: Mapping[int, str] = field(default_factory=dict)
    external_items: Mapping[int, bool] = field(default_factory=dict)
    external_evidence_refs: Mapping[int, str] = field(default_factory=dict)
    pilot_metrics: Mapping[str, bool] = field(default_factory=dict)
    pilot_evidence_refs: Mapping[str, str] = field(default_factory=dict)
    signoffs: Mapping[str, bool] = field(default_factory=dict)
    signoff_evidence_refs: Mapping[str, str] = field(default_factory=dict)


def _verified_items(
    values: Mapping[int, bool],
    evidence_refs: Mapping[int, str],
    required: tuple[int, ...],
) -> bool:
    return all(values.get(item, False) and evidence_refs.get(item, "").strip() for item in required)


def _verified_named(
    values: Mapping[str, bool],
    evidence_refs: Mapping[str, str],
    required: tuple[str, ...],
) -> bool:
    return all(values.get(key, False) and evidence_refs.get(key, "").strip() for key in required)


def can_create_production_candidate(truth: ReleaseTruth) -> bool:
    return (
        truth.repository_green
        and bool(truth.repository_evidence_ref.strip())
        and _verified_items(truth.sre_items, truth.sre_evidence_refs, REQUIRED_SRE)
        and _verified_items(
            truth.external_items,
            truth.external_evidence_refs,
            REQUIRED_EXTERNAL,
        )
    )


def can_start_pilot(truth: ReleaseTruth) -> bool:
    return can_create_production_candidate(truth)


def can_accept_pilot(truth: ReleaseTruth) -> bool:
    return can_create_production_candidate(truth) and _verified_named(
        truth.pilot_metrics,
        truth.pilot_evidence_refs,
        PILOT_METRICS,
    )


def _controlled(values: tuple[str, ...]) -> bool:
    normalized = {value.strip().lower() for value in values if value.strip()}
    forbidden = {"*", "all", "all-tenants", "all-modules"}
    return bool(normalized) and not (forbidden & normalized)


def can_activate_production(
    truth: ReleaseTruth,
    *,
    tenant_ids: tuple[str, ...],
    modules: tuple[str, ...],
) -> bool:
    return (
        can_accept_pilot(truth)
        and _controlled(tenant_ids)
        and _controlled(modules)
        and _verified_named(
            truth.signoffs,
            truth.signoff_evidence_refs,
            PROD_SIGNOFFS,
        )
    )


def next_state(
    current: ReleaseState,
    truth: ReleaseTruth,
    *,
    tenant_ids: tuple[str, ...] = (),
    modules: tuple[str, ...] = (),
) -> ReleaseState:
    if current == ReleaseState.DEVELOPMENT:
        if not can_create_production_candidate(truth):
            raise ValueError("production candidate blocked by repository/SRE/external evidence")
        return ReleaseState.PRODUCTION_CANDIDATE
    if current == ReleaseState.PRODUCTION_CANDIDATE:
        if not can_start_pilot(truth):
            raise ValueError("pilot start blocked because release evidence is no longer valid")
        return ReleaseState.PILOT
    if current == ReleaseState.PILOT:
        if not can_accept_pilot(truth):
            raise ValueError("pilot acceptance evidence incomplete")
        return ReleaseState.PILOT_ACCEPTED
    if current == ReleaseState.PILOT_ACCEPTED:
        if not can_activate_production(
            truth,
            tenant_ids=tenant_ids,
            modules=modules,
        ):
            raise ValueError("controlled production activation blocked")
        return ReleaseState.PRODUCTION_ACTIVE
    if current == ReleaseState.PRODUCTION_ACTIVE:
        return ReleaseState.STABILIZING
    raise ValueError("state transition requires explicit category-leadership iteration")


Priority = Literal["P0", "P1", "P2"]


@dataclass(frozen=True)
class StabilizationIssue:
    source: str
    category: str
    description: str
    evidence_ref: str
    priority: Priority


def stabilization_backlog(
    issues: tuple[StabilizationIssue, ...],
) -> tuple[StabilizationIssue, ...]:
    order = {"P0": 0, "P1": 1, "P2": 2}
    return tuple(
        sorted(
            (issue for issue in issues if issue.evidence_ref.strip()),
            key=lambda issue: (order[issue.priority], issue.category, issue.source),
        )
    )


@dataclass(frozen=True)
class BenchmarkSignal:
    source: str
    category: str
    observed_change: str
    evidence_ref: str


def category_leadership_backlog(
    signals: tuple[BenchmarkSignal, ...],
) -> tuple[BenchmarkSignal, ...]:
    return tuple(
        sorted(
            (signal for signal in signals if signal.evidence_ref.strip()),
            key=lambda signal: (
                signal.category,
                signal.source,
                signal.observed_change,
            ),
        )
    )
