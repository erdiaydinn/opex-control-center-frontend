import pytest

from app.modules.field_intelligence.evidence_access import (
    EvidenceAccessError,
    EvidenceObjectRef,
    EvidenceReadAuthority,
    authorize_evidence_read,
)


def ref(tenant="tenant-a", location="store-1", mission="mission-1", key="tenant-a/mission-1/evidence/photo-1"):
    return EvidenceObjectRef(
        tenant_id=tenant,
        mission_id=mission,
        location_id=location,
        evidence_id="photo-1",
        object_key=key,
        object_hash="a" * 64,
    )


def authority():
    return EvidenceReadAuthority(
        tenant_id="tenant-a",
        subject_id="manager-1",
        allowed_location_ids=frozenset({"store-1"}),
        allowed_mission_ids=frozenset({"mission-1"}),
    )


def test_authorized_private_object_reference_can_reach_signing_layer():
    assert authorize_evidence_read(ref(), authority=authority()).object_key.startswith("tenant-a/")


def test_cross_tenant_location_or_mission_read_is_rejected():
    with pytest.raises(EvidenceAccessError, match="tenant"):
        authorize_evidence_read(ref(tenant="tenant-b"), authority=authority())
    with pytest.raises(EvidenceAccessError, match="location"):
        authorize_evidence_read(ref(location="store-2"), authority=authority())
    with pytest.raises(EvidenceAccessError, match="mission"):
        authorize_evidence_read(ref(mission="mission-2"), authority=authority())


def test_public_evidence_url_is_never_accepted_as_storage_authority():
    with pytest.raises(EvidenceAccessError, match="public URL"):
        authorize_evidence_read(ref(key="https://public.example/photo.jpg"), authority=authority())
