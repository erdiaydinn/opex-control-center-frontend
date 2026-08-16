from datetime import datetime, timezone

import pytest

from app.modules.field_intelligence.authorization import (
    MissionAuthorAuthority,
    MissionAuthorizationError,
    authorize_target_snapshot,
)
from app.modules.field_intelligence.models import TargetSnapshot

NOW = datetime(2026, 8, 16, 12, 30, tzinfo=timezone.utc)


def snapshot(tenant="tenant-a", locations=("store-1", "store-2")):
    return TargetSnapshot(
        tenant_id=tenant,
        created_at=NOW,
        location_ids=locations,
        fingerprint="a" * 64,
    )


def test_manager_can_target_only_locations_in_server_authoritative_scope():
    authority = MissionAuthorAuthority(
        tenant_id="tenant-a",
        actor_id="regional-manager-1",
        allowed_location_ids=frozenset({"store-1", "store-2", "store-3"}),
    )
    assert authorize_target_snapshot(snapshot(), authority=authority).location_ids == ("store-1", "store-2")


def test_cross_region_or_location_scope_escape_is_rejected():
    authority = MissionAuthorAuthority(
        tenant_id="tenant-a",
        actor_id="district-manager-1",
        allowed_location_ids=frozenset({"store-1"}),
    )
    with pytest.raises(MissionAuthorizationError, match="outside actor authority"):
        authorize_target_snapshot(snapshot(locations=("store-1", "store-2")), authority=authority)


def test_cross_tenant_target_snapshot_is_rejected_even_if_location_id_matches():
    authority = MissionAuthorAuthority(
        tenant_id="tenant-a",
        actor_id="manager-1",
        allowed_location_ids=frozenset({"store-1"}),
    )
    with pytest.raises(MissionAuthorizationError, match="tenant"):
        authorize_target_snapshot(snapshot(tenant="tenant-b", locations=("store-1",)), authority=authority)
