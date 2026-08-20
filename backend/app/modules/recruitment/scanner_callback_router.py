"""Priority ingress for recruitment scanner service callbacks.

The callback has three independent authorities: authenticated service identity
with an explicit permission, KMS HMAC receipt verification, and the dedicated
V43 PostgreSQL scanner role. Normal HR identities never gain scanner authority.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .candidate_scan_authority import CandidateScanAuthorityError, record_verified_scan
from .request_evidence_scan_authority import (
    RequestEvidenceScanAuthorityError,
    record_verified_request_scan,
)
from .router import _require


router = APIRouter(prefix="/recruitment", tags=["Recruitment Scanner Authority"])
_SCANNER_PERMISSION = "submitRecruitmentScannerReceipt"


class ScannerReceiptEnvelope(BaseModel):
    payload: dict[str, str]
    signature: str = Field(min_length=1, max_length=256)


def _require_scanner_service(role: str, permissions: str) -> None:
    # No normal HR role has this action in the built-in role map; a service
    # identity must receive it explicitly from verified OIDC permission claims.
    _require(role, permissions, _SCANNER_PERMISSION)


@router.post("/candidate-evidence/scanner-receipts", include_in_schema=False)
def candidate_scanner_receipt(
    envelope: ScannerReceiptEnvelope,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_scanner_service(x_opex_role, x_opex_permissions)
    try:
        evidence = record_verified_scan(
            envelope.payload,
            envelope.signature,
            actor="recruitment-scanner",
        )
        return {
            "accepted": True,
            "evidence_id": evidence.get("id"),
            "content_safety_state": evidence.get("content_safety_state"),
        }
    except CandidateScanAuthorityError as error:
        raise HTTPException(status_code=409, detail="Scanner receipt reddedildi.") from error


@router.post("/requests/{request_id}/evidence/scanner-receipts", include_in_schema=False)
def request_scanner_receipt(
    request_id: str,
    envelope: ScannerReceiptEnvelope,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_scanner_service(x_opex_role, x_opex_permissions)
    try:
        evidence = record_verified_request_scan(
            request_id,
            envelope.payload,
            envelope.signature,
        )
        return {
            "accepted": True,
            "evidence_id": evidence.get("id"),
            "content_safety_state": evidence.get("content_safety_state"),
        }
    except RequestEvidenceScanAuthorityError as error:
        raise HTTPException(status_code=409, detail="Scanner receipt reddedildi.") from error
