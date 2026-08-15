from datetime import datetime, timezone

import pytest

from app.modules.field_intelligence.evidence import (
    EvidenceAuthorityContext,
    EvidenceCaptureSource,
    EvidenceItem,
    EvidenceKind,
    EvidencePolicy,
    EvidenceValidationError,
    EvidenceVerification,
    VerificationDecision,
    build_evidence_envelope,
)

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)


def authority(*, tenant="tenant-a", actor="employee-1", locations=frozenset({"store-1"}), devices=frozenset({"device-1"})):
    return EvidenceAuthorityContext(
        tenant_id=tenant,
        actor_id=actor,
        allowed_location_ids=locations,
        trusted_device_ids=devices,
    )


def item(*, tenant="tenant-a", location="store-1", actor="employee-1", device="device-1", source=EvidenceCaptureSource.CAMERA, lat=41.0, lon=29.0):
    return EvidenceItem(
        evidence_id="photo-1",
        tenant_id=tenant,
        mission_id="lot-check-001",
        location_id=location,
        actor_id=actor,
        device_id=device,
        kind=EvidenceKind.PHOTO,
        capture_source=source,
        captured_at=NOW,
        value="private://evidence/photo-1",
        object_hash="a" * 64,
        latitude=lat,
        longitude=lon,
    )


def test_camera_managed_device_and_location_policy_accepts_bound_evidence():
    envelope = build_evidence_envelope(
        policy=EvidencePolicy(
            required_kinds=(EvidenceKind.PHOTO,),
            camera_only_photo=True,
            managed_device_required=True,
            location_proof_required=True,
        ),
        tenant_id="tenant-a",
        mission_id="lot-check-001",
        location_id="store-1",
        actor_id="employee-1",
        device_id="device-1",
        authority=authority(),
        submitted_at=NOW,
        items=(item(),),
    )
    assert envelope.fingerprint
    assert envelope.tenant_id == "tenant-a"


def test_managed_device_string_without_authoritative_device_trust_is_rejected():
    with pytest.raises(EvidenceValidationError, match="not trusted"):
        build_evidence_envelope(
            policy=EvidencePolicy(managed_device_required=True),
            tenant_id="tenant-a",
            mission_id="lot-check-001",
            location_id="store-1",
            actor_id="employee-1",
            device_id="device-spoofed",
            authority=authority(devices=frozenset({"device-1"})),
            submitted_at=NOW,
            items=(item(device="device-spoofed"),),
        )


def test_authoritative_location_scope_is_enforced_before_capture_is_accepted():
    with pytest.raises(EvidenceValidationError, match="not authorized"):
        build_evidence_envelope(
            policy=EvidencePolicy(),
            tenant_id="tenant-a",
            mission_id="lot-check-001",
            location_id="store-1",
            actor_id="employee-1",
            authority=authority(locations=frozenset({"store-2"})),
            submitted_at=NOW,
            items=(item(),),
        )


def test_cross_tenant_evidence_reuse_fails_closed():
    with pytest.raises(EvidenceValidationError, match="scope"):
        build_evidence_envelope(
            policy=EvidencePolicy(required_kinds=(EvidenceKind.PHOTO,)),
            tenant_id="tenant-a",
            mission_id="lot-check-001",
            location_id="store-1",
            actor_id="employee-1",
            submitted_at=NOW,
            items=(item(tenant="tenant-b"),),
        )


def test_gallery_photo_is_rejected_when_camera_only_policy_is_enabled():
    with pytest.raises(EvidenceValidationError, match="captured by camera"):
        build_evidence_envelope(
            policy=EvidencePolicy(camera_only_photo=True),
            tenant_id="tenant-a",
            mission_id="lot-check-001",
            location_id="store-1",
            actor_id="employee-1",
            submitted_at=NOW,
            items=(item(source=EvidenceCaptureSource.MANUAL),),
        )


def test_location_proof_policy_rejects_missing_coordinates():
    with pytest.raises(EvidenceValidationError, match="location proof"):
        build_evidence_envelope(
            policy=EvidencePolicy(location_proof_required=True),
            tenant_id="tenant-a",
            mission_id="lot-check-001",
            location_id="store-1",
            actor_id="employee-1",
            submitted_at=NOW,
            items=(item(lat=None, lon=None),),
        )


def test_rework_and_reject_require_human_reason():
    with pytest.raises(ValueError, match="requires a reason"):
        EvidenceVerification(
            tenant_id="tenant-a",
            mission_id="lot-check-001",
            location_id="store-1",
            envelope_fingerprint="b" * 64,
            reviewer_id="manager-1",
            decision=VerificationDecision.REWORK,
            reviewed_at=NOW,
        )
