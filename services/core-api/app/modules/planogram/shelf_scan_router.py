from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.execution import PlanogramExecutionError
from app.modules.planogram.shelf_scan import evaluate_shelf_scan
from app.modules.planogram.shelf_scan_schemas import PlanogramShelfScanPreviewRequest

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])

ShelfScanReviewer = Annotated[
    Principal,
    Depends(require_permission("action:planogram:edit")),
]


@router.post("/shelf-scan-preview")
async def post_planogram_shelf_scan_preview(
    payload: PlanogramShelfScanPreviewRequest,
    principal: ShelfScanReviewer,
) -> dict[str, object]:
    """Compare vision observations with a Planogram without creating field truth."""
    try:
        result = evaluate_shelf_scan(
            plan_payload=payload.plan_payload,
            shelves=[row.model_dump(mode="python") for row in payload.shelves],
            observations=[
                row.model_dump(mode="python") for row in payload.observations
            ],
            min_detection_confidence=payload.min_detection_confidence,
            min_image_quality=payload.min_image_quality,
            max_occlusion_pct=payload.max_occlusion_pct,
        )
    except PlanogramExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.code,
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_detector_observation_unattested",
        "production_evidence": False,
        "field_truth_write_allowed": False,
        "auto_accept_allowed": False,
        "auto_correct_allowed": False,
        "human_review_required_for_deviation_action": True,
        "result": result,
    }
