from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.field_intelligence.authorization import require_field_permission
from app.modules.field_intelligence.evidence_object_upload import (
    MAX_EVIDENCE_BYTES,
    FieldEvidenceStoreUnavailable,
    FieldEvidenceUploadError,
    upload_private_evidence_object,
)
from app.modules.field_intelligence.repository import list_locations

router = APIRouter(prefix="/v1/field/evidence-objects", tags=["field-evidence-objects"])
FieldViewer = Annotated[
    Principal,
    Depends(require_permission("module:field_intelligence:view")),
]


@router.post("/{field_key}", status_code=status.HTTP_201_CREATED)
async def post_field_evidence_object(
    field_key: str,
    request: Request,
    principal: FieldViewer,
    mission_id: UUID,
    location_id: str,
    client_submission_id: UUID,
    content_sha256: Annotated[str, Header(alias="X-EAY-Content-SHA256")],
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:submitEvidence")
    locations = await list_locations(str(principal.tenant_id), scope)
    allowed_ids = {str(item["location_id"]) for item in locations}
    if location_id not in allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Field evidence object location is outside authorized scope",
        )
    if len(content_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in content_sha256
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field evidence object SHA-256 header is invalid",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Field evidence object content length is invalid",
            ) from exc
        if declared_length <= 0 or declared_length > MAX_EVIDENCE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Field evidence object exceeds the upload limit",
            )

    content = await request.body()
    if len(content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Field evidence object exceeds the upload limit",
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
            detail="Private Field evidence storage is unavailable",
        ) from exc

    return {
        **receipt,
        "authority": "server_issued_private_evidence_receipt",
        "public_url": None,
        "production_storage_evidence": False,
    }
