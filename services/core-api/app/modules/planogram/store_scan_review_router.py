from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.store_dna import normalize_store_code
from app.modules.planogram.store_scan_annotation import build_reviewed_store_scan_draft
from app.modules.planogram.store_scan_review_schemas import (
    PlanogramStoreScanAnnotationPreviewRequest,
)

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
Creator = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]


@router.post("/store-scan/annotate-preview")
async def post_store_scan_annotation_preview(
    payload: PlanogramStoreScanAnnotationPreviewRequest,
    principal: Creator,
) -> dict[str, object]:
    """Apply human annotations and uncertainty decisions to a fingerprint-bound scan."""
    try:
        result = build_reviewed_store_scan_draft(
            scan_payload=payload.scan.model_dump(mode="python"),
            expected_scan_fingerprint=payload.expected_scan_fingerprint,
            classifications=[row.model_dump(mode="python") for row in payload.classifications],
            operational_elements=[
                row.model_dump(mode="python") for row in payload.operational_elements
            ],
            review_note=payload.review_note,
            uncertainty_resolutions=[
                row.model_dump(mode="python") for row in payload.uncertainty_resolutions
            ],
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram Store Scan review validator is unavailable",
        ) from exc

    if result.get("store_dna_authority") is not False:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram Store Scan review violated Store DNA authority boundary",
        )
    if result.get("production_authority") is not False:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram Store Scan review violated production authority boundary",
        )

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": normalize_store_code(payload.scan.store_code),
        "preview_only": True,
        "input_authority": "fingerprint_bound_human_review_unattested",
        "store_dna_approval_allowed": False,
        "production_release_allowed": False,
        "installation_approval_allowed": False,
        "result": result,
    }
