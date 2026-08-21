from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceObjectRef(BaseModel):
    tenant_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=3)
    location_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=3)
    object_key: str = Field(min_length=1, max_length=1024)
    object_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceReadAuthority(BaseModel):
    tenant_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    allowed_location_ids: frozenset[str] = Field(min_length=1)
    allowed_mission_ids: frozenset[str] = Field(default_factory=frozenset)


class EvidenceAccessError(PermissionError):
    pass


def authorize_evidence_read(
    ref: EvidenceObjectRef,
    *,
    authority: EvidenceReadAuthority,
) -> EvidenceObjectRef:
    """Authorize before object-storage layer creates a short-lived private URL."""
    if ref.tenant_id != authority.tenant_id:
        raise EvidenceAccessError("evidence tenant is outside principal authority")
    if ref.location_id not in authority.allowed_location_ids:
        raise EvidenceAccessError("evidence location is outside principal authority")
    if authority.allowed_mission_ids and ref.mission_id not in authority.allowed_mission_ids:
        raise EvidenceAccessError("evidence mission is outside principal authority")
    if ref.object_key.startswith(("http://", "https://")):
        raise EvidenceAccessError("evidence object key must not be a public URL")
    return ref
