from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.authorization import require_permission
from app.core.security import Principal

from .authorization import require_audit_scope, scope_allows_location
from .privacy_verification_runtime import AuditPrivacyEvidenceScanner
from .privacy_verification_service import verify_bound_redaction_receipt
from .repository import AuditRepositoryError
from .resource_scope import get_run_location

router = APIRouter(prefix="/v1/audit", tags=["audit-privacy"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


def _server_privacy_scanner(request: Request) -> AuditPrivacyEvidenceScanner:
    """Resolve the server-owned scanner without accepting scanner authority from the client."""

    scanner = getattr(request.app.state, "audit_privacy_scanner", None)
    if scanner is None or not callable(getattr(scanner, "scan_jpeg", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server Audit privacy scanner is not configured",
        )
    return cast(AuditPrivacyEvidenceScanner, scanner)


@router.post(
    "/runs/{audit_run_id}/redaction-receipts/{redaction_receipt_id}/verify-privacy"
)
async def post_server_privacy_verification(
    audit_run_id: UUID,
    redaction_receipt_id: UUID,
    request: Request,
    principal: AuditViewer,
) -> dict[str, object]:
    """Trigger server-owned privacy verification for one immutable sanitized evidence object.

    The caller may request verification but cannot provide a verification result, scanner identity,
    model fingerprint or downstream vision authorization. Those values are server-derived only.
    """

    scope = require_audit_scope(principal, "action:audit:submitEvidence")
    location = await get_run_location(str(principal.tenant_id), audit_run_id)
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit run not found")
    location_id = str(location.get("location_id") or "")
    region = str(location.get("region") or "") or None
    if not location_id or not scope_allows_location(
        scope,
        location_id=location_id,
        region=region,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit privacy verification is outside authorized scope",
        )

    scanner = _server_privacy_scanner(request)
    try:
        return await verify_bound_redaction_receipt(
            tenant_id=str(principal.tenant_id),
            audit_run_id=audit_run_id,
            redaction_receipt_id=redaction_receipt_id,
            scanner=scanner,
        )
    except AuditRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
