from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OfflineSyncDecision(StrEnum):
    ACCEPT = "accept"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    CONFLICT = "conflict"


class OfflineEvent(BaseModel):
    tenant_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=3)
    location_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    device_sequence: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=200)
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime


class ExistingOfflineEvent(BaseModel):
    tenant_id: str
    device_id: str
    device_sequence: int
    idempotency_key: str
    payload_hash: str


class OfflineSyncResult(BaseModel):
    decision: OfflineSyncDecision
    reason: str


def reconcile_offline_event(event: OfflineEvent, existing: ExistingOfflineEvent | None) -> OfflineSyncResult:
    if existing is None:
        return OfflineSyncResult(decision=OfflineSyncDecision.ACCEPT, reason="new device sequence")
    if existing.tenant_id != event.tenant_id or existing.device_id != event.device_id:
        return OfflineSyncResult(decision=OfflineSyncDecision.CONFLICT, reason="existing sequence scope mismatch")
    if existing.device_sequence != event.device_sequence:
        return OfflineSyncResult(decision=OfflineSyncDecision.CONFLICT, reason="existing sequence identity mismatch")
    if existing.idempotency_key == event.idempotency_key and existing.payload_hash == event.payload_hash:
        return OfflineSyncResult(decision=OfflineSyncDecision.IDEMPOTENT_REPLAY, reason="exact replay")
    return OfflineSyncResult(
        decision=OfflineSyncDecision.CONFLICT,
        reason="device sequence was already consumed by different payload",
    )
