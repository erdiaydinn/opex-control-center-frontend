from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field
from sqlalchemy import text

from app.core.authorization import require_permission
from app.core.resources import engine
from app.core.security import Principal
from app.modules.field_intelligence.evidence_object_upload import (
    FieldEvidenceStoreUnavailable,
)
from app.modules.field_intelligence.repository import _set_tenant

from .authorization import require_audit_scope, scope_allows_location
from .privacy_verification_runtime import AuditPrivacyEvidenceScanner
from .repository import AuditConflictError, AuditRepositoryError
from .resource_scope import get_run_location
from .schemas import StrictModel
from .video_verification_runtime import AuditPrivateVideoDecoder
from .video_verification_service import verify_bound_video_receipt
from .video_vision_authorization import (
    authorize_video_vision_inference,
    consume_video_vision_authorization,
)

router = APIRouter(prefix="/v1/audit", tags=["audit-video"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


class AuditVideoVisionAuthorizationCreate(StrictModel):
    redaction_receipt_id: UUID
    video_verification_event_id: UUID


class AuditVideoVisionAuthorizationConsume(StrictModel):
    authorization_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


def _server_video_decoder(request: Request) -> AuditPrivateVideoDecoder:
    decoder = getattr(request.app.state, "audit_video_decoder", None)
    if decoder is None or not callable(getattr(decoder, "decode_mp4", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server Audit video decoder is not configured",
        )
    return cast(AuditPrivateVideoDecoder, decoder)


def _server_privacy_scanner(request: Request) -> AuditPrivacyEvidenceScanner:
    scanner = getattr(request.app.state, "audit_privacy_scanner", None)
    if scanner is None or not callable(getattr(scanner, "scan_jpeg", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server Audit privacy scanner is not configured",
        )
    return cast(AuditPrivacyEvidenceScanner, scanner)


async def _require_run_scope(
    principal: Principal,
    permission: str,
    audit_run_id: UUID,
) -> None:
    scope = require_audit_scope(principal, permission)
    location = await get_run_location(str(principal.tenant_id), audit_run_id)
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit run not found",
        )
    location_id = str(location.get("location_id") or "")
    region = str(location.get("region") or "") or None
    if not location_id or not scope_allows_location(
        scope,
        location_id=location_id,
        region=region,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit video resource is outside authorized scope",
        )


async def _authorization_belongs_to_run(
    *,
    tenant_id: str,
    audit_run_id: UUID,
    authorization_id: UUID,
) -> bool:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT 1
                FROM audit_video_inference_authorizations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:authorization_id AS UUID)
                  AND audit_run_id = CAST(:audit_run_id AS UUID)
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "authorization_id": str(authorization_id),
            },
        )
        return result.first() is not None


@router.post(
    "/runs/{audit_run_id}/redaction-receipts/{redaction_receipt_id}/verify-video-privacy"
)
async def post_server_video_privacy_verification(
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
    request: Request,
    principal: AuditViewer,
) -> dict[str, object]:
    """Verify immutable MP4 evidence using only server-owned decode/privacy authority."""

    await _require_run_scope(
        principal,
        "action:audit:submitEvidence",
        audit_run_id,
    )
    decoder = _server_video_decoder(request)
    scanner = _server_privacy_scanner(request)
    try:
        return await verify_bound_video_receipt(
            tenant_id=str(principal.tenant_id),
            audit_run_id=audit_run_id,
            redaction_receipt_id=redaction_receipt_id,
            decoder=decoder,
            scanner=scanner,
        )
    except FieldEvidenceStoreUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Private Audit video evidence is unavailable",
        ) from exc
    except AuditRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/runs/{audit_run_id}/items/{item_key}/video-vision-authorizations"
)
async def post_video_vision_authorization(
    audit_run_id: UUID,
    item_key: str,
    payload: AuditVideoVisionAuthorizationCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    """Issue a single-use model lease; this endpoint cannot assert a finding or action."""

    await _require_run_scope(
        principal,
        "action:audit:decideItem",
        audit_run_id,
    )
    try:
        decision = await authorize_video_vision_inference(
            tenant_id=str(principal.tenant_id),
            audit_run_id=audit_run_id,
            item_key=item_key,
            redaction_receipt_id=payload.redaction_receipt_id,
            video_verification_event_id=payload.video_verification_event_id,
        )
        return asdict(decision)
    except AuditRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/runs/{audit_run_id}/video-vision-authorizations/{authorization_id}/consume"
)
async def post_consume_video_vision_authorization(
    audit_run_id: UUID,
    authorization_id: UUID,
    payload: AuditVideoVisionAuthorizationConsume,
    principal: AuditViewer,
) -> dict[str, object]:
    """Consume one exact video model lease once, fenced to the run in the request path."""

    await _require_run_scope(
        principal,
        "action:audit:decideItem",
        audit_run_id,
    )
    tenant_id = str(principal.tenant_id)
    if not await _authorization_belongs_to_run(
        tenant_id=tenant_id,
        audit_run_id=audit_run_id,
        authorization_id=authorization_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video vision authorization not found for Audit run",
        )
    try:
        return await consume_video_vision_authorization(
            tenant_id=tenant_id,
            authorization_id=authorization_id,
            authorization_fingerprint=payload.authorization_fingerprint,
        )
    except (AuditConflictError, AuditRepositoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
