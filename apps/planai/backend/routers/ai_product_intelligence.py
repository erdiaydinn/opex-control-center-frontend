
from fastapi import APIRouter, Body, Query
from typing import Any, Dict
from services.product_similarity import decide_product, find_similar_products, reload_similarity_index

router = APIRouter(prefix="/ai", tags=["ai-product-intelligence"])

@router.post("/similar-products")
def similar_products(payload: Dict[str, Any] = Body(...), limit: int = Query(12, ge=1, le=50)):
    product = payload.get("product") or payload
    return {"status": "success", **find_similar_products(product, limit=limit)}

@router.post("/product-decision")
def product_decision(payload: Dict[str, Any] = Body(...), limit: int = Query(16, ge=3, le=50)):
    product = payload.get("product") or payload
    return {"status": "success", **decide_product(product, limit=limit)}

@router.post("/council/product-review")
def council_product_review(payload: Dict[str, Any] = Body(...)):
    product = payload.get("product") or payload
    decision = decide_product(product, limit=int(payload.get("limit", 16)))
    d = decision["decision"]
    return {
        "status": "success",
        "council": {
            "decision": "approved" if d["confidence"] >= 0.72 else "approved_with_warning",
            "confidence": d["confidence"],
            "agents": [
                {"name": "Storage Guardian", "verdict": d["storage_type"], "reason": decision["why"][1]},
                {"name": "Fixture Architect", "verdict": d["dimensions"], "reason": decision["why"][2]},
                {"name": "Sales Optimizer", "verdict": {"facing": d["facing"]}, "reason": decision["why"][3]},
                {"name": "Skeptic Auditor", "verdict": "manual_check" if d["confidence"] < 0.72 else "no_blocker", "reason": "Benzer ürün güveni düşükse saha ölçüsü veya kategori kontrolü gerekir."},
            ],
            "similar_products": decision["similar_products"],
            "why": decision["why"],
        },
    }

@router.post("/similarity-index/reload")
def reload_index():
    return reload_similarity_index()
