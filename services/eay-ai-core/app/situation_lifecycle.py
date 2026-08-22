"""Cross-run lifecycle state for evidence-bound Jarvis situations.

Detection is intentionally stateless. This module provides an append-safe state
projection so the same object-centric situation can be tracked as new, ongoing,
resolved, or reopened without turning absence/presence into Company World truth,
causal proof, replanning authority, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .situation_detection import SituationCandidate

SITUATION_LIFECYCLE_CONTRACT = "eay-situation-lifecycle-v1"


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


class SituationLifecycleStatus(str, Enum):
    NEW = "new"
    ONGOING = "ongoing"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class SituationLifecycleRecord(BaseModel):
    lifecycle_key: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    status: SituationLifecycleStatus
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    occurrence_count: int = Field(ge=1)
    latest_candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    truth_authority_granted: bool = False
    replanning_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def record_is_temporal_non_authoritative_and_integral(self) -> "SituationLifecycleRecord":
        _aware(self.first_seen_at, "situation_lifecycle_first_seen_requires_timezone")
        _aware(self.last_seen_at, "situation_lifecycle_last_seen_requires_timezone")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("situation_lifecycle_last_seen_before_first_seen")
        if self.resolved_at is not None:
            _aware(self.resolved_at, "situation_lifecycle_resolved_at_requires_timezone")
            if self.resolved_at < self.last_seen_at:
                raise ValueError("situation_lifecycle_resolved_before_last_seen")
        if self.status is SituationLifecycleStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("situation_lifecycle_resolved_requires_timestamp")
        if self.status is not SituationLifecycleStatus.RESOLVED and self.resolved_at is not None:
            raise ValueError("situation_lifecycle_active_record_cannot_have_resolved_at")
        if self.truth_authority_granted or self.replanning_authority_granted or self.execution_authority_granted:
            raise ValueError("situation_lifecycle_never_grants_authority")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("situation_lifecycle_evidence_refs_must_be_unique")
        expected = _canonical_hash(self.model_dump(mode="json", exclude={"fingerprint"}))
        if self.fingerprint != expected:
            raise ValueError("situation_lifecycle_record_fingerprint_mismatch")
        return self


class SituationLifecycleSnapshot(BaseModel):
    contract: str = SITUATION_LIFECYCLE_CONTRACT
    tenant_id: str = Field(min_length=1)
    as_of: datetime
    records: tuple[SituationLifecycleRecord, ...]
    truth_authority_granted: bool = False
    replanning_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def snapshot_is_non_authoritative_and_integral(self) -> "SituationLifecycleSnapshot":
        _aware(self.as_of, "situation_lifecycle_as_of_requires_timezone")
        if self.truth_authority_granted or self.replanning_authority_granted or self.execution_authority_granted:
            raise ValueError("situation_lifecycle_never_grants_authority")
        keys = [item.lifecycle_key for item in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("situation_lifecycle_keys_must_be_unique")
        if any(item.tenant_id != self.tenant_id for item in self.records):
            raise ValueError("situation_lifecycle_cross_tenant_record_forbidden")
        if any(item.first_seen_at > self.as_of or item.last_seen_at > self.as_of for item in self.records):
            raise ValueError("situation_lifecycle_record_from_future")
        expected = _canonical_hash(self.model_dump(mode="json", exclude={"fingerprint"}))
        if self.fingerprint != expected:
            raise ValueError("situation_lifecycle_snapshot_fingerprint_mismatch")
        return self


def _key(tenant_id: str, object_ref: str) -> str:
    return f"situation:{tenant_id}:{object_ref}"


def _sealed_record(**payload) -> SituationLifecycleRecord:
    draft = SituationLifecycleRecord.model_construct(**payload, fingerprint="0" * 64)
    fingerprint = _canonical_hash(draft.model_dump(mode="json", exclude={"fingerprint"}))
    return SituationLifecycleRecord(**payload, fingerprint=fingerprint)


def _sealed_snapshot(*, tenant_id: str, as_of: datetime, records: tuple[SituationLifecycleRecord, ...]) -> SituationLifecycleSnapshot:
    ordered = tuple(sorted(records, key=lambda item: item.lifecycle_key))
    payload = dict(tenant_id=tenant_id, as_of=as_of, records=ordered)
    draft = SituationLifecycleSnapshot.model_construct(**payload, fingerprint="0" * 64)
    fingerprint = _canonical_hash(draft.model_dump(mode="json", exclude={"fingerprint"}))
    return SituationLifecycleSnapshot(**payload, fingerprint=fingerprint)


def new_situation_lifecycle(*, tenant_id: str, as_of: datetime) -> SituationLifecycleSnapshot:
    _aware(as_of, "situation_lifecycle_as_of_requires_timezone")
    return _sealed_snapshot(tenant_id=tenant_id, as_of=as_of, records=())


def advance_situation_lifecycle(
    *,
    previous: SituationLifecycleSnapshot,
    candidates: tuple[SituationCandidate, ...],
    as_of: datetime,
    resolve_after_seconds: int = 900,
) -> SituationLifecycleSnapshot:
    _aware(as_of, "situation_lifecycle_as_of_requires_timezone")
    if resolve_after_seconds < 1:
        raise ValueError("situation_lifecycle_resolve_after_must_be_positive")
    previous = SituationLifecycleSnapshot.model_validate(previous.model_dump(mode="json"))
    if as_of < previous.as_of:
        raise ValueError("situation_lifecycle_cannot_move_backward")

    validated: dict[str, SituationCandidate] = {}
    for raw in candidates:
        candidate = SituationCandidate.model_validate(raw.model_dump(mode="json"))
        if candidate.tenant_id != previous.tenant_id:
            raise ValueError("situation_lifecycle_cross_tenant_candidate_forbidden")
        if candidate.detected_at > as_of:
            raise ValueError("situation_lifecycle_candidate_from_future")
        key = _key(candidate.tenant_id, candidate.object_ref)
        if key in validated:
            raise ValueError("situation_lifecycle_duplicate_current_object")
        validated[key] = candidate

    old = {item.lifecycle_key: item for item in previous.records}
    all_keys = sorted(set(old) | set(validated))
    updated: list[SituationLifecycleRecord] = []
    resolve_after = timedelta(seconds=resolve_after_seconds)

    for key in all_keys:
        prior = old.get(key)
        candidate = validated.get(key)
        if candidate is not None:
            candidate_ref = f"situation-candidate://{candidate.fingerprint}"
            if prior is None:
                updated.append(
                    _sealed_record(
                        lifecycle_key=key,
                        tenant_id=candidate.tenant_id,
                        object_ref=candidate.object_ref,
                        status=SituationLifecycleStatus.NEW,
                        first_seen_at=candidate.detected_at,
                        last_seen_at=candidate.detected_at,
                        occurrence_count=1,
                        latest_candidate_fingerprint=candidate.fingerprint,
                        evidence_refs=tuple(dict.fromkeys((*candidate.evidence_refs, candidate_ref))),
                    )
                )
                continue
            if candidate.detected_at < prior.last_seen_at:
                raise ValueError("situation_lifecycle_candidate_precedes_last_seen")
            if candidate.fingerprint == prior.latest_candidate_fingerprint:
                updated.append(prior)
                continue
            status = (
                SituationLifecycleStatus.REOPENED
                if prior.status is SituationLifecycleStatus.RESOLVED
                else SituationLifecycleStatus.ONGOING
            )
            updated.append(
                _sealed_record(
                    lifecycle_key=key,
                    tenant_id=prior.tenant_id,
                    object_ref=prior.object_ref,
                    status=status,
                    first_seen_at=prior.first_seen_at,
                    last_seen_at=candidate.detected_at,
                    occurrence_count=prior.occurrence_count + 1,
                    latest_candidate_fingerprint=candidate.fingerprint,
                    evidence_refs=tuple(dict.fromkeys((*prior.evidence_refs, *candidate.evidence_refs, candidate_ref))),
                )
            )
            continue

        assert prior is not None
        if prior.status is SituationLifecycleStatus.RESOLVED:
            updated.append(prior)
            continue
        if as_of - prior.last_seen_at < resolve_after:
            updated.append(prior)
            continue
        updated.append(
            _sealed_record(
                lifecycle_key=prior.lifecycle_key,
                tenant_id=prior.tenant_id,
                object_ref=prior.object_ref,
                status=SituationLifecycleStatus.RESOLVED,
                first_seen_at=prior.first_seen_at,
                last_seen_at=prior.last_seen_at,
                resolved_at=as_of,
                occurrence_count=prior.occurrence_count,
                latest_candidate_fingerprint=prior.latest_candidate_fingerprint,
                evidence_refs=prior.evidence_refs,
            )
        )

    return _sealed_snapshot(
        tenant_id=previous.tenant_id,
        as_of=as_of,
        records=tuple(updated),
    )
