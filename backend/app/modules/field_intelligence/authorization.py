from __future__ import annotations

from pydantic import BaseModel, Field

from .models import TargetSnapshot


class MissionAuthorAuthority(BaseModel):
    """Server-derived authority for HQ/manager mission creation."""

    tenant_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    allowed_location_ids: frozenset[str] = Field(min_length=1)
    can_target_all_allowed_locations: bool = True


class MissionAuthorizationError(PermissionError):
    pass


def authorize_target_snapshot(
    snapshot: TargetSnapshot,
    *,
    authority: MissionAuthorAuthority,
) -> TargetSnapshot:
    if snapshot.tenant_id != authority.tenant_id:
        raise MissionAuthorizationError("target snapshot tenant is outside actor authority")
    unauthorized = set(snapshot.location_ids) - set(authority.allowed_location_ids)
    if unauthorized:
        raise MissionAuthorizationError(
            f"mission targets locations outside actor authority: {', '.join(sorted(unauthorized))}"
        )
    return snapshot
