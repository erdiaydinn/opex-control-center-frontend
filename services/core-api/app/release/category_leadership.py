"""Master 56-60 release, pilot, activation, stabilization, and leadership authority."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from app.sre.chaos_dr import (
    ChaosResult,
    DrResult,
    chaos_result_accepted,
    dr_result_accepted,
)
from app.sre.governance import AcceptanceEvidence, production_shape_evidence_satisfied
from app.sre.observability import TelemetryEvent, validate_telemetry_event


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
_KIND = re.compile(r"^[a-z][a-z0-9_-]*$")
_FORBIDDEN_SCOPE = {"*", "all", "all-tenants", "all-modules"}
_FORBIDDEN_EVIDENCE_ENV = {"ci", "repository", "synthetic"}


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


def _artifact_digest(value: str) -> str:
    if not _SHA64.fullmatch(value):
        raise ValueError("artifact digest must be lowercase SHA-256")
    return value


def _validate_release_identity(release_id: str, candidate_sha: str) -> None:
    if not release_id.strip():
        raise ValueError("release_id is required")
    if not _SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be an exact lowercase 40-character commit SHA")


def _release_id_digest(release_id: str) -> str:
    if not release_id.strip():
        raise ValueError("release_id is required")
    return hashlib.sha256(release_id.encode()).hexdigest()


def bind_release_evidence_ref(
    kind: str,
    *,
    release_id: str,
    candidate_sha: str,
    artifact_sha256: str,
) -> str:
    """Bind a proof artifact to one release ID and one exact candidate SHA."""

    _validate_release_identity(release_id, candidate_sha)
    if not _KIND.fullmatch(kind):
        raise ValueError("invalid release evidence kind")
    return ":".join(
        (
            f"{kind}-sha256",
            candidate_sha,
            _release_id_digest(release_id),
            _artifact_digest(artifact_sha256),
        )
    )


def bind_authority_ref(
    kind: str,
    source_ref: str,
    *,
    release_id: str,
    candidate_sha: str,
) -> str:
    """Bind an accepted 45-55 authority fingerprint to the active release."""

    marker = f"{kind}-sha256:"
    if not source_ref.startswith(marker):
        raise ValueError("authority fingerprint kind mismatch")
    source_digest = source_ref[len(marker) :]
    return bind_release_evidence_ref(
        kind,
        release_id=release_id,
        candidate_sha=candidate_sha,
        artifact_sha256=source_digest,
    )


def _bound_ref(value: str, kind: str, truth: ReleaseTruth) -> bool:
    parts = value.split(":")
    return (
        len(parts) == 4
        and parts[0] == f"{kind}-sha256"
        and parts[1] == truth.candidate_sha
        and parts[2] == _release_id_digest(truth.release_id)
        and bool(_SHA64.fullmatch(parts[3]))
    )


def _sre_ref(item: int, artifact_sha256: str, parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256(
        "|".join((str(item), _artifact_digest(artifact_sha256), *parts)).encode()
    ).hexdigest()
    return f"sre-sha256:{digest}"


def build_observability_item_ref(
    contract: dict[str, object],
    events: tuple[TelemetryEvent, ...],
    *,
    artifact_sha256: str,
) -> str:
    """Build Master 45 evidence only from full, non-synthetic telemetry coverage."""

    if not events:
        raise ValueError("observability evidence events are required")
    environments = {event.environment.strip().casefold() for event in events}
    if len(environments) != 1 or environments & _FORBIDDEN_EVIDENCE_ENV:
        raise ValueError("observability evidence must come from one governed environment")

    for event in events:
        validate_telemetry_event(contract, event)
    required = {str(value) for value in contract["required_signals"]}
    observed = {event.signal for event in events}
    if not required <= observed:
        raise ValueError("observability evidence does not cover every required signal")

    parts = tuple(
        sorted(
            ":".join(
                (
                    event.signal,
                    event.service,
                    event.environment,
                    event.workflow,
                    event.operation,
                    event.result,
                    ",".join(f"{key}={value}" for key, value in sorted(event.dimensions.items())),
                )
            )
            for event in events
        )
    )
    return _sre_ref(45, artifact_sha256, parts)


def build_scale_item_ref(
    registry: dict[str, object],
    evidence_by_key: Mapping[str, AcceptanceEvidence],
    *,
    artifact_sha256: str,
) -> str:
    """Build Master 46 evidence only when every governed production-shape test passes."""

    tests = tuple(registry.get("production_shape_tests", ()))
    if not tests:
        raise ValueError("production-shape tests are required")
    parts: list[str] = []
    for profile in tests:
        key = str(profile.get("key", ""))
        evidence = evidence_by_key.get(key)
        if evidence is None or not production_shape_evidence_satisfied(profile, evidence):
            raise ValueError(f"production-shape evidence failed: {key}")
        parts.append(
            ":".join(
                (
                    key,
                    evidence.evidence_class,
                    evidence.environment,
                    str(evidence.measured),
                    evidence.provenance,
                )
            )
        )
    return _sre_ref(46, artifact_sha256, tuple(sorted(parts)))


def build_chaos_item_ref(
    contract: dict[str, object],
    results: tuple[ChaosResult, ...],
    *,
    artifact_sha256: str,
) -> str:
    """Build Master 47 evidence only when all governed chaos scenarios pass."""

    expected = {str(value) for value in contract.get("chaos_scenarios", ())}
    by_scenario = {result.scenario: result for result in results}
    if not expected or set(by_scenario) != expected or len(by_scenario) != len(results):
        raise ValueError("chaos evidence must cover each governed scenario exactly once")
    if not all(chaos_result_accepted(contract, result) for result in results):
        raise ValueError("one or more governed chaos scenarios failed")

    parts = tuple(
        sorted(
            ":".join(
                (
                    result.scenario,
                    result.environment,
                    str(result.measured),
                    ",".join(sorted(result.passed_invariants)),
                    result.provenance,
                )
            )
            for result in results
        )
    )
    return _sre_ref(47, artifact_sha256, parts)


def build_dr_item_ref(result: DrResult, *, artifact_sha256: str) -> str:
    """Build Master 48 evidence only from measured, governed restore/RPO/RTO proof."""

    if not dr_result_accepted(result):
        raise ValueError("DR evidence is not accepted")
    parts = (
        result.environment,
        str(result.restore_passed),
        str(result.rpo_seconds),
        str(result.rto_seconds),
        result.provenance,
    )
    return _sre_ref(48, artifact_sha256, parts)


def _controlled(values: tuple[str, ...]) -> bool:
    normalized = {value.strip().lower() for value in values if value.strip()}
    return bool(normalized) and not (_FORBIDDEN_SCOPE & normalized)


def _scope_valid(scope: ReleaseScope | None, truth: ReleaseTruth) -> bool:
    return bool(
        scope
        and _controlled(scope.tenant_ids)
        and _controlled(scope.modules)
        and _bound_ref(scope.evidence_ref, "scope", truth)
        and scope.owner.strip()
    )


def _scope_contains(
    scope: ReleaseScope | None,
    *,
    truth: ReleaseTruth,
    tenant_ids: tuple[str, ...],
    modules: tuple[str, ...],
) -> bool:
    if (
        not _scope_valid(scope, truth)
        or not _controlled(tenant_ids)
        or not _controlled(modules)
    ):
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
    truth: ReleaseTruth,
    ref_prefix: str,
) -> bool:
    return all(
        values.get(item, False)
        and _bound_ref(evidence_refs.get(item, ""), ref_prefix, truth)
        for item in required
    )


def _verified_named(
    values: Mapping[str, bool],
    evidence_refs: Mapping[str, str],
    required: tuple[str, ...],
    *,
    truth: ReleaseTruth,
    ref_prefix: str,
) -> bool:
    return all(
        values.get(key, False)
        and _bound_ref(evidence_refs.get(key, ""), ref_prefix, truth)
        for key in required
    )


def can_create_production_candidate(truth: ReleaseTruth) -> bool:
    try:
        _validate_release_identity(truth.release_id, truth.candidate_sha)
    except ValueError:
        return False
    return (
        truth.repository_green
        and truth.repository_evidence_ref == f"github-status:{truth.candidate_sha}"
        and _verified_items(
            truth.sre_items,
            truth.sre_evidence_refs,
            REQUIRED_SRE,
            truth=truth,
            ref_prefix="sre",
        )
        and _verified_items(
            truth.external_items,
            truth.external_evidence_refs,
            REQUIRED_EXTERNAL,
            truth=truth,
            ref_prefix="ledger",
        )
    )


def can_start_pilot(truth: ReleaseTruth) -> bool:
    return (
        can_create_production_candidate(truth)
        and _scope_valid(truth.pilot_scope, truth)
        and _bound_ref(truth.pilot_plan_ref, "plan", truth)
        and _bound_ref(truth.pilot_rollback_ref, "rollback", truth)
    )


def can_accept_pilot(truth: ReleaseTruth) -> bool:
    return can_start_pilot(truth) and _verified_named(
        truth.pilot_metrics,
        truth.pilot_evidence_refs,
        PILOT_METRICS,
        truth=truth,
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
            truth=truth,
            tenant_ids=tenant_ids,
            modules=modules,
        )
        and _scope_contains(
            truth.activation_scope,
            truth=truth,
            tenant_ids=tenant_ids,
            modules=modules,
        )
        and _bound_ref(truth.activation_plan_ref, "plan", truth)
        and _bound_ref(truth.activation_rollback_ref, "rollback", truth)
        and _verified_named(
            truth.signoffs,
            truth.signoff_evidence_refs,
            PROD_SIGNOFFS,
            truth=truth,
            ref_prefix="signoff",
        )
    )


def can_accept_stabilization(truth: ReleaseTruth) -> bool:
    scope = truth.activation_scope
    if not _scope_valid(scope, truth):
        return False
    assert scope is not None
    return can_activate_production(
        truth,
        tenant_ids=scope.tenant_ids,
        modules=scope.modules,
    ) and _verified_named(
        truth.stabilization_metrics,
        truth.stabilization_evidence_refs,
        STABILIZATION_METRICS,
        truth=truth,
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
            raise ValueError(
                "pilot start requires bounded scope, plan, rollback, and valid evidence"
            )
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
            raise ValueError("stabilization or active release evidence incomplete")
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
