from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    engine_status,
    generate_preview,
)
from app.modules.planogram.schemas import PlanogramPreviewRequest

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])

Viewer = Annotated[
    Principal,
    Depends(require_permission("module:planogram:view")),
]
Creator = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]

REQUIRED_EVIDENCE = (
    "approved_sku_dimensions",
    "product_image_linkage",
    "store_dna",
    "fixture_geometry_capacity",
    "physical_layout_aisle",
    "pallet_fixture_authority",
)


def _engine_or_503() -> dict[str, object]:
    try:
        return engine_status()
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical Planogram engine is unavailable",
        ) from exc


@router.get("/readiness")
async def get_planogram_readiness(principal: Viewer) -> dict[str, object]:
    """Expose software readiness without inventing physical production truth."""
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "engine": _engine_or_503(),
        "authority_state": "no_server_attested_physical_truth",
        "production_ready": False,
        "publishable": False,
        "solver_optimizer_allowed": False,
        "physical_truth": {
            "server_attested": False,
            "required_evidence": list(REQUIRED_EVIDENCE),
        },
    }


@router.post("/preview")
async def post_planogram_preview(
    payload: PlanogramPreviewRequest,
    principal: Creator,
) -> dict[str, object]:
    """Run the canonical physical gate against request-supplied candidate data.

    A successful candidate solve is still not production evidence. Production
    release remains disabled until an EAY server-attested master/layout/Store
    DNA chain exists outside caller-controlled request payloads.
    """
    _engine_or_503()
    try:
        result = generate_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            mode=payload.mode,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical Planogram engine is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "production_release_allowed": False,
        "engine_result": result,
    }
