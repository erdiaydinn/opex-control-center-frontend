"""Master 56-60 release, pilot, activation, stabilization, and leadership authority."""

from __future__ import annotations

import re
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
    CATEGORY_LEADERSHIP = "CATEGORY_LEADERSHIP"


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
STABILIZATION_METRICS = (
    "error_budget",
    "incident_rate",
    "reconciliation",
    "support_backlog",
    "no_open_p0",
    "rollback_readiness",
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_SCOPE = {"*", "all", "all-tenants", "all-modules"}


@dataclass(frozen=True)
class ReleaseScope:
    tenant_ids: tuple[str, ...]
    modules: tuple[str, ...]
    evidence_ref: str
    owner: str


@dataclass(frozen=True)
class ReleaseTruth:
    release_id: str
    candidate_sha: str
    repository_green: bool
    repository_evidence_ref: str = ""
    sre_items: Mapping[int, bool] = field(default_factory=dict)
    sre_evidence_refs: Mapping[int, str] = field(default_factory=dict)
    external_items: Mapping[int, bool] = field(default_factory=dict)
    external_evidence_refs: Mapping[int, str] = field(default_factory=dict)
    pilot_scope: ReleaseScope | None = None
    pilot_plan_ref: str = ""
    pilot_rollback_ref: str = ""
    pilot_metrics: Mapping[str, bool] = field(default_factory=dict)
    pilot_evidence_refs: Mapping[str, str] = field(default_factory=dict)
    activation_scope: ReleaseScope | None = None
    activation_plan_ref: str = ""
    activation_rollback_ref: str = ""
    signoffs: Mapping[str, bool] = field(default_factory=dict)
    signoff_evidence_refs: Mapping[str, str] = field(default_factory=dict)
    stabilization_metrics: Mapping[str, bool] = field(default_factory=dict)
    stabilization_evidence_refs: Mapping[str, str] = field(default_factory=dict)


def _hash_ref(value: str, prefix: str) -> bool:
    marker = f"{prefix}-sha256:"
    return value.startswith(marker) and bool(_SHA64.fullmatch(value[len(marker) :]))


def _controlled(values: tuple[str, ...]) -> bool:
    normalized = {value.strip().lower() for value in values if value.strip()}
    return bool(normalized) and not (_FORBIDDEN_SCOPE & normalized)


def _scope_valid(scope: ReleaseScope | None) -> bool:
    return bool(
        scope
        and _controlled(scope.tenant_ids)
        and _controlled(scope.modules)
        and _hash_ref(scope.evidence_ref, "scope")
        and scope.owner.strip()
    )


def _scope_contains(
    scope: ReleaseScope | None,
    *,
    tenant_ids: tuple[str, ...],
    modules: tuple[str, ...],
) -> bool:
    if not _scope_valid(scope) or not _controlled(tenant_ids) or not _controlled(modules):
        return False
    assert scope is not None
    allowed_tenants = {value.strip().lower() for value in scope.tenant_ids}
    allowed_modules = {value.strip().lower() for value in scope.modules}
    requested_tenants = {value.strip().lower() for value in tenant_ids}
    requested_modules = {value.strip().lower() for value in modules}
    return requested_tenants <= allowed_tenants and requested_modules <= allowed_modules


def _verified_items(
    values: Mapping[int, bool],
    evidence_refs: Mapping[int, str],
    required: tuple[int, ...],
    *,
    ref_prefix: str,
) -> bool:
    return all(
        values.get(item, False)
        and _hash_ref(evidence_refs.get(item, ""), ref_prefix)
        for item in required
    )


def _verified_named(
    values: Mapping[str, bool],
    evidence_refs: Mapping[str, str],
    required: tuple[str, ...],
    *,
    ref_prefix: str,
) -> bool:
    return all(
        values.get(key, False)
        and _hash_ref(evidence_refs.get(key, ""), ref_prefix)
        for key in required
    )


def can_create_production_candidate(truth: ReleaseTruth) -> bool:
    return (
        bool(truth.release_id.strip())
        and bool(_SHA40.fullmatch(truth.candidate_sha))
        and truth.repository_green
        and truth.repository_evidence_ref == f"github-status:{truth.candidate_sha}"
        and _verified_items(
            truth.sre_items,
            truth.sre_evidence_refs,
            REQUIRED_SRE,
            ref_prefix="sre",
        )
        and _verified_items(
            truth.external_items,
            truth.external_evidence_refs,
            REQUIRED_EXTERNAL,
            ref_prefix="ledger",
        )
    )


def can_start_pilot(truth: ReleaseTruth) -> bool:
    return (
        can_create_production_candidate(truth)
        and _scope_valid(truth.pilot_scope)
        and _hash_ref(truth.pilot_plan_ref, "plan")
        and _hash_ref(truth.pilot_rollback_ref, "rollback")
    )


def can_accept_pilot(truth: ReleaseTruth) -> bool:
    return can_start_pilot(truth) and _verified_named(
        truth.pilot_metrics,
        truth.pilot_evidence_refs,
        PILOT_METRICS,
        ref_prefix="pilot",
    )


def can_activate_production(
    truth: ReleaseTruth,
    *,
    tenant_ids: tuple[str, ...],
    modules: tuple[str, ...],
) -> bool:
    return (
        can_accept_pilot(truth)
        and _scope_contains(
            truth.pilot_scope,
            tenant_ids=tenant_ids,
            modules=modules,
        )
        and _scope_contains(
            truth.activation_scope,
            tenant_ids=tenant_ids,
            modules=modules,
        )
        and _hash_ref(truth.activation_plan_ref, "plan")
        and _hash_ref(truth.activation_rollback_ref, "rollback")
        and _verified_named(
            truth.signoffs,
            truth.signoff_evidence_refs,
            PROD_SIGNOFFS,
            ref_prefix="signoff",
        )
    )


def can_accept_stabilization(truth: ReleaseTruth) -> bool:
    return _verified_named(
        truth.stabilization_metrics,
        truth.stabilization_evidence_refs,
        STABILIZATION_METRICS,
        ref_prefix="stabilization",
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
            raise ValueError("pilot start requires bounded scope, plan, rollback, and valid evidence")
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
    if current == ReleaseState.STABILIZING:
        if not can_accept_stabilization(truth):
            raise ValueError("stabilization acceptance evidence incomplete")
        return ReleaseState.CATEGORY_LEADERSHIP
    raise ValueError("category leadership is a continuous governed iteration state")


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
            (
                issue
                for issue in issues
                if _hash_ref(issue.evidence_ref, "stabilization")
            ),
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
            (
                signal
                for signal in signals
                if _hash_ref(signal.evidence_ref, "benchmark")
            ),
            key=lambda signal: (
                signal.category,
                signal.source,
                signal.observed_change,
            ),
        )
    )
