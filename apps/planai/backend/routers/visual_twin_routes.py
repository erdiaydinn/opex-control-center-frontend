from fastapi import APIRouter, Body
from typing import Any, Dict

from services.visual_twin_payload import build_visual_twin_payload

router = APIRouter(prefix="/visual-twin", tags=["visual-twin"])


@router.post("/scene-payload")
def scene_payload(payload: Dict[str, Any] = Body(...)):
    return build_visual_twin_payload(
        planogram_result=payload.get("planogram_result") or payload.get("result") or {},
        merged_products=payload.get("merged_products") or [],
        excluded_products=payload.get("excluded_products") or [],
        review_products=payload.get("review_products") or [],
    )