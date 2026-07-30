
from fastapi import APIRouter, Body
from typing import Any, Dict, List
from services.dimension_sanity import sanitize_dimensions

router = APIRouter(prefix="/ai", tags=["ai-dimension-sanity"])

@router.post("/dimension-sanity")
def dimension_sanity(payload: Dict[str, Any] = Body(...)):
    product = payload.get("product") or payload
    similar_decision = payload.get("similar_decision")
    return {
        "status": "success",
        "product": sanitize_dimensions(product, similar_decision=similar_decision),
    }

@router.post("/dimension-sanity/batch")
def dimension_sanity_batch(payload: Dict[str, Any] = Body(...)):
    products = payload.get("products") or []
    fixed = [sanitize_dimensions(p) for p in products]
    return {
        "status": "success",
        "count": len(fixed),
        "fixed_count": sum(1 for p in fixed if (p.get("ai_sanity") or {}).get("fixed")),
        "products": fixed,
    }
