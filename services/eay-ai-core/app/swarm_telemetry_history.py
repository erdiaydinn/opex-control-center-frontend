"""Append-only, cutoff-safe history for Jarvis swarm execution pressure.

A telemetry snapshot is orchestration evidence, never Company World truth. This
module retains only the already-sanitized aggregate metrics needed to understand
whether swarm pressure is rising, stable or falling across rounds. Historical
queries use both observation and recording time so late/future evidence cannot
leak into replay.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .swarm_execution_telemetry import SwarmExecutionTelemetrySnapshot

SWARM_TELEMETRY_HISTORY_CONTRACT = "eay-swarm-telemetry-history-v1"


def _canonical_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


class PressureTrendDirection(str, Enum):
    INSUFFICIENT = "insufficient"
    FALLING = "falling"
    STABLE = "stable"
    RISING = "rising"


class SwarmTelemetryHistoryEntry(BaseModel):
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    recorded_at: datetime
    operational_pressure_score: float = Field(ge=0.0, le=1.0)
    admitted_lane_count: int = Field(ge=0)
    deferred_lane_count: int = Field(ge=0)
    held_lease_count: int = Field(ge=0)
    released_lease_count: int = Field(ge=0)
    total_transitions_executed: int = Field(ge=0)
    blocker_codes: tuple[str, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def entry_is_temporal_and_integral(self) -> "SwarmTelemetryHistoryEntry":
        _aware(self.observed_at, "swarm_telemetry_history_observed_at_requires_timezone")
        _aware(self.recorded_at, "swarm_telemetry_history_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("swarm_telemetry_history_recorded_before_observed")
        if len(self.blocker_codes) != len(set(self.blocker_codes)):
            raise ValueError("swarm_telemetry_history_blocker_codes_must_be_unique")
        expected = _canonical_hash(self.model_dump(mode="json", exclude={"fingerprint"}))
        if self.fingerprint != expected:
            raise ValueError("swarm_telemetry_history_entry_fingerprint_mismatch")
        return self


class SwarmTelemetryHistory(BaseModel):
    contract: str = SWARM_TELEMETRY_HISTORY_CONTRACT
    tenant_id: str = Field(min_length=1)
    entries: tuple[SwarmTelemetryHistoryEntry, ...] = ()
    raw_payload_retained: bool = False
    business_values_retained: bool = False
    credential_material_retained: bool = False
    authoritative_truth_surface: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def history_is_non_authoritative_and_integral(self) -> "SwarmTelemetryHistory":
        if self.raw_payload_retained or self.business_values_retained or self.credential_material_retained:
            raise ValueError("swarm_telemetry_history_cannot_retain_sensitive_content")
        if self.authoritative_truth_surface:
            raise ValueError("swarm_telemetry_history_never_becomes_business_truth")
        if self.execution_authority_granted:
            raise ValueError("swarm_telemetry_history_never_grants_execution_authority")
        fingerprints = [item.snapshot_fingerprint for item in self.entries]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("swarm_telemetry_history_snapshot_fingerprints_must_be_unique")
        if tuple(sorted(self.entries, key=lambda item: (item.recorded_at, item.observed_at, item.snapshot_fingerprint))) != self.entries:
            raise ValueError("swarm_telemetry_history_entries_must_be_ordered")
        expected = _canonical_hash(self.model_dump(mode="json", exclude={"fingerprint"}))
        if self.fingerprint != expected:
            raise ValueError("swarm_telemetry_history_fingerprint_mismatch")
        return self


class SwarmPressureTrend(BaseModel):
    contract: str = SWARM_TELEMETRY_HISTORY_CONTRACT
    tenant_id: str
    as_of: datetime
    sample_count: int = Field(ge=0)
    direction: PressureTrendDirection
    earliest_pressure_score: float | None = Field(default=None, ge=0.0, le=1.0)
    latest_pressure_score: float | None = Field(default=None, ge=0.0, le=1.0)
    pressure_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    held_lease_delta: int = 0
    deferred_lane_delta: int = 0
    blocker_codes: tuple[str, ...] = ()
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def trend_is_non_authoritative(self) -> "SwarmPressureTrend":
        _aware(self.as_of, "swarm_pressure_trend_as_of_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("swarm_pressure_trend_never_grants_execution_authority")
        if self.sample_count < 2 and self.direction is not PressureTrendDirection.INSUFFICIENT:
            raise ValueError("swarm_pressure_trend_requires_two_samples")
        if self.sample_count >= 2 and self.direction is PressureTrendDirection.INSUFFICIENT:
            raise ValueError("swarm_pressure_trend_sufficient_samples_cannot_be_insufficient")
        return self


def _sealed_entry(*, snapshot: SwarmExecutionTelemetrySnapshot, recorded_at: datetime) -> SwarmTelemetryHistoryEntry:
    payload = dict(
        snapshot_fingerprint=snapshot.fingerprint,
        observed_at=snapshot.observed_at,
        recorded_at=recorded_at,
        operational_pressure_score=snapshot.operational_pressure_score,
        admitted_lane_count=snapshot.admitted_lane_count,
        deferred_lane_count=snapshot.globally_deferred_lane_count,
        held_lease_count=snapshot.held_lease_count,
        released_lease_count=snapshot.released_lease_count,
        total_transitions_executed=snapshot.total_transitions_executed,
        blocker_codes=snapshot.blocker_codes,
    )
    draft = SwarmTelemetryHistoryEntry.model_construct(**payload, fingerprint="0" * 64)
    fingerprint = _canonical_hash(draft.model_dump(mode="json", exclude={"fingerprint"}))
    return SwarmTelemetryHistoryEntry(**payload, fingerprint=fingerprint)


def _sealed_history(*, tenant_id: str, entries: tuple[SwarmTelemetryHistoryEntry, ...]) -> SwarmTelemetryHistory:
    payload = dict(tenant_id=tenant_id, entries=entries)
    draft = SwarmTelemetryHistory.model_construct(**payload, fingerprint="0" * 64)
    fingerprint = _canonical_hash(draft.model_dump(mode="json", exclude={"fingerprint"}))
    return SwarmTelemetryHistory(**payload, fingerprint=fingerprint)


def new_swarm_telemetry_history(*, tenant_id: str) -> SwarmTelemetryHistory:
    return _sealed_history(tenant_id=tenant_id, entries=())


def append_swarm_telemetry(
    *,
    history: SwarmTelemetryHistory,
    snapshot: SwarmExecutionTelemetrySnapshot,
    recorded_at: datetime,
) -> SwarmTelemetryHistory:
    _aware(recorded_at, "swarm_telemetry_history_recorded_at_requires_timezone")
    history = SwarmTelemetryHistory.model_validate(history.model_dump(mode="json"))
    snapshot = SwarmExecutionTelemetrySnapshot.model_validate(snapshot.model_dump(mode="json"))
    if snapshot.tenant_id != history.tenant_id:
        raise ValueError("swarm_telemetry_history_cross_tenant_snapshot_forbidden")
    if recorded_at < snapshot.observed_at:
        raise ValueError("swarm_telemetry_history_recorded_before_observed")
    existing = next(
        (item for item in history.entries if item.snapshot_fingerprint == snapshot.fingerprint),
        None,
    )
    if existing is not None:
        candidate = _sealed_entry(snapshot=snapshot, recorded_at=recorded_at)
        if candidate.model_dump(mode="json", exclude={"recorded_at", "fingerprint"}) != existing.model_dump(mode="json", exclude={"recorded_at", "fingerprint"}):
            raise ValueError("swarm_telemetry_history_snapshot_identity_mutated")
        return history

    entry = _sealed_entry(snapshot=snapshot, recorded_at=recorded_at)
    entries = tuple(sorted((*history.entries, entry), key=lambda item: (item.recorded_at, item.observed_at, item.snapshot_fingerprint)))
    return _sealed_history(tenant_id=history.tenant_id, entries=entries)


def swarm_pressure_trend(
    *,
    history: SwarmTelemetryHistory,
    as_of: datetime,
    stable_delta: float = 0.05,
) -> SwarmPressureTrend:
    _aware(as_of, "swarm_pressure_trend_as_of_requires_timezone")
    if not 0.0 <= stable_delta <= 1.0:
        raise ValueError("swarm_pressure_trend_stable_delta_out_of_range")
    history = SwarmTelemetryHistory.model_validate(history.model_dump(mode="json"))
    visible = tuple(
        item
        for item in history.entries
        if item.observed_at <= as_of and item.recorded_at <= as_of
    )
    blockers = tuple(sorted({code for item in visible for code in item.blocker_codes}))
    if len(visible) < 2:
        latest = visible[-1] if visible else None
        return SwarmPressureTrend(
            tenant_id=history.tenant_id,
            as_of=as_of,
            sample_count=len(visible),
            direction=PressureTrendDirection.INSUFFICIENT,
            earliest_pressure_score=None if latest is None else latest.operational_pressure_score,
            latest_pressure_score=None if latest is None else latest.operational_pressure_score,
            blocker_codes=blockers,
        )

    earliest = visible[0]
    latest = visible[-1]
    delta = round(latest.operational_pressure_score - earliest.operational_pressure_score, 6)
    if delta > stable_delta:
        direction = PressureTrendDirection.RISING
    elif delta < -stable_delta:
        direction = PressureTrendDirection.FALLING
    else:
        direction = PressureTrendDirection.STABLE
    return SwarmPressureTrend(
        tenant_id=history.tenant_id,
        as_of=as_of,
        sample_count=len(visible),
        direction=direction,
        earliest_pressure_score=earliest.operational_pressure_score,
        latest_pressure_score=latest.operational_pressure_score,
        pressure_delta=delta,
        held_lease_delta=latest.held_lease_count - earliest.held_lease_count,
        deferred_lane_delta=latest.deferred_lane_count - earliest.deferred_lane_count,
        blocker_codes=blockers,
    )
