from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class EvidenceKind(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    BARCODE = "barcode"
    QR = "qr"
    LOT = "lot"
    SERIAL = "serial"
    EXPIRY = "expiry"
    QUANTITY = "quantity"
    GPS = "gps"
    MEASUREMENT = "measurement"


class EvidenceCaptureSource(StrEnum):
    CAMERA = "camera"
    SCANNER = "scanner"
    DEVICE_SENSOR = "device_sensor"
    MANUAL = "manual"


class VerificationDecision(StrEnum):
    ACCEPT = "accept"
    REWORK = "rework"
    REJECT = "reject"


class EvidencePolicy(BaseModel):
    required_kinds: tuple[EvidenceKind, ...] = ()
    camera_only_photo: bool = False
    managed_device_required: bool = False
    location_proof_required: bool = False
    manager_verification_required: bool = False


class EvidenceAuthorityContext(BaseModel):
    """Server-derived authority supplied by central identity/device services."""

    tenant_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    allowed_location_ids: frozenset[str] = Field(min_length=1)
    trusted_device_ids: frozenset[str] = frozenset()


class EvidenceItem(BaseModel):
    evidence_id: str = Field(min_length=3, max_length=120)
    tenant_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=3)
    location_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    device_id: str | None = None
    kind: EvidenceKind
    capture_source: EvidenceCaptureSource
    captured_at: datetime
    value: str = Field(min_length=1, max_length=2048)
    object_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_coordinates(self) -> "EvidenceItem":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class EvidenceEnvelope(BaseModel):
    tenant_id: str
    mission_id: str
    location_id: str
    actor_id: str
    device_id: str | None = None
    submitted_at: datetime
    items: tuple[EvidenceItem, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceVerification(BaseModel):
    tenant_id: str
    mission_id: str
    location_id: str
    envelope_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_id: str = Field(min_length=1)
    decision: VerificationDecision
    reason: str | None = Field(default=None, max_length=500)
    reviewed_at: datetime

    @model_validator(mode="after")
    def require_reason_for_non_accept(self) -> "EvidenceVerification":
        if self.decision is not VerificationDecision.ACCEPT and not (self.reason and self.reason.strip()):
            raise ValueError("rework/reject verification requires a reason")
        return self


class EvidenceValidationError(ValueError):
    pass


def build_evidence_envelope(
    *,
    policy: EvidencePolicy,
    tenant_id: str,
    mission_id: str,
    location_id: str,
    actor_id: str,
    submitted_at: datetime,
    items: tuple[EvidenceItem, ...],
    device_id: str | None = None,
    authority: EvidenceAuthorityContext | None = None,
) -> EvidenceEnvelope:
    if authority is not None:
        if authority.tenant_id != tenant_id or authority.actor_id != actor_id:
            raise EvidenceValidationError("central authority does not match evidence tenant/actor")
        if location_id not in authority.allowed_location_ids:
            raise EvidenceValidationError("actor is not authorized for evidence location")

    if policy.managed_device_required:
        if not device_id:
            raise EvidenceValidationError("managed device evidence is required")
        if authority is None or device_id not in authority.trusted_device_ids:
            raise EvidenceValidationError("managed device is not trusted by authoritative device service")

    if not items:
        raise EvidenceValidationError("at least one physical evidence item is required")

    present_kinds = {item.kind for item in items}
    missing = set(policy.required_kinds) - present_kinds
    if missing:
        raise EvidenceValidationError(f"missing evidence kinds: {', '.join(sorted(kind.value for kind in missing))}")

    for item in items:
        if item.tenant_id != tenant_id or item.mission_id != mission_id or item.location_id != location_id:
            raise EvidenceValidationError("evidence item scope does not match submission scope")
        if item.actor_id != actor_id:
            raise EvidenceValidationError("evidence actor does not match submission actor")
        if device_id and item.device_id not in {None, device_id}:
            raise EvidenceValidationError("evidence device does not match submission device")
        if policy.camera_only_photo and item.kind is EvidenceKind.PHOTO and item.capture_source is not EvidenceCaptureSource.CAMERA:
            raise EvidenceValidationError("photo evidence must be captured by camera")
        if policy.location_proof_required and item.latitude is None:
            raise EvidenceValidationError("location proof is required for every evidence item")

    canonical = "|".join(
        [tenant_id, mission_id, location_id, actor_id, device_id or "", submitted_at.isoformat()]
        + [
            ":".join(
                [
                    item.evidence_id,
                    item.kind.value,
                    item.capture_source.value,
                    item.value,
                    item.object_hash or "",
                    item.captured_at.isoformat(),
                ]
            )
            for item in sorted(items, key=lambda entry: entry.evidence_id)
        ]
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return EvidenceEnvelope(
        tenant_id=tenant_id,
        mission_id=mission_id,
        location_id=location_id,
        actor_id=actor_id,
        device_id=device_id,
        submitted_at=submitted_at,
        items=items,
        fingerprint=fingerprint,
    )
