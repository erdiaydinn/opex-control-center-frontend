from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import text

from app.core.authorization import require_permission
from app.core.resources import engine
from app.core.security import Principal
from app.modules.field_intelligence.evidence_object_upload import (
    MAX_EVIDENCE_BYTES,
    FieldEvidenceStoreUnavailable,
    FieldEvidenceUploadError,
    upload_private_evidence_object,
)
from app.modules.field_intelligence.repository import _set_tenant

from .authorization import require_audit_scope, scope_allows_location
from .resource_scope import get_run_location

router = APIRouter(prefix="/v1/audit", tags=["audit-evidence-objects"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


async def _run_evidence_authority(
    tenant_id: str,
    audit_run_id: UUID,
) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT ar.id AS audit_run_id, ar.field_mission_id, ar.location_id,
                       ar.status, fl.region
                FROM audit_runs ar
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                  AND ar.id = CAST(:audit_run_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "audit_run_id": str(audit_run_id)},
        )
        row = result.mappings().first()
        return dict(row) if row else None


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@router.post(
    "/runs/{audit_run_id}/evidence-objects/{field_key}",
    status_code=status.HTTP_201_CREATED,
)
async def post_audit_evidence_object(
    audit_run_id: UUID,
    field_key: str,
    request: Request,
    principal: AuditViewer,
    client_submission_id: UUID,
    content_sha256: Annotated[str, Header(alias="X-EAY-Content-SHA256")],
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:submitEvidence")
    scoped_location = await get_run_location(str(principal.tenant_id), audit_run_id)
    if not scoped_location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit run not found")
    location_id = str(scoped_location.get("location_id") or "")
    region = str(scoped_location.get("region") or "") or None
    if not scope_allows_location(scope, location_id=location_id, region=region):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit evidence run is outside authorized scope",
        )

    authority = await _run_evidence_authority(str(principal.tenant_id), audit_run_id)
    if not authority or authority.get("status") == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audit run cannot accept evidence",
        )
    mission_id = authority.get("field_mission_id")
    if mission_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audit run has no governed Field mission for private evidence storage",
        )
    if not _valid_sha256(content_sha256):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audit evidence SHA-256 header is invalid",
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audit evidence content length is invalid",
            ) from exc
        if declared_length <= 0 or declared_length > MAX_EVIDENCE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Audit evidence object exceeds the upload limit",
            )

    content = await request.body()
    if not content or len(content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audit evidence object size is invalid",
        )

    try:
        receipt = await upload_private_evidence_object(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            mission_id=str(mission_id),
            location_id=location_id,
            client_submission_id=str(client_submission_id),
            field_key=field_key,
            media_type=request.headers.get("content-type", ""),
            expected_sha256=content_sha256,
            content=content,
        )
    except FieldEvidenceUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FieldEvidenceStoreUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Private Audit evidence storage is unavailable",
        ) from exc

    return {
        **receipt,
        "audit_run_id": str(audit_run_id),
        "location_id": location_id,
        "field_mission_id": str(mission_id),
        "redacted_evidence_ref": f"field-evidence-receipt:{receipt['receipt_id']}",
        "authority": "server_issued_private_evidence_receipt",
        "client_redaction_claim_only": True,
        "server_privacy_verified": False,
        "vision_inference_authorized": False,
        "public_url": None,
        "production_storage_evidence": False,
    }
