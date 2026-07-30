from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body
from pydantic import BaseModel

from intelligence_core_v19 import (
    compare_shelf_change,
    product_placement_confidence,
    resolve_fixture_target,
    score_planogram_intelligence,
    sort_suggestions_by_confidence,
)

router = APIRouter(prefix="/intelligence-v19", tags=["intelligence-v19"])


class PlanogramScoreRequest(BaseModel):
    planogram: Dict[str, Any]


class ProductConfidenceRequest(BaseModel):
    product: Dict[str, Any]
    aisle: Optional[Dict[str, Any]] = None
    module: Optional[Dict[str, Any]] = None
    shelf: Optional[Dict[str, Any]] = None
    existing_products: Optional[List[Dict[str, Any]]] = None


class ShelfImpactRequest(BaseModel):
    shelf: Dict[str, Any]
    candidate_product: Dict[str, Any]
    current_product: Optional[Dict[str, Any]] = None
    aisle: Optional[Dict[str, Any]] = None
    module: Optional[Dict[str, Any]] = None


class SuggestionSortRequest(BaseModel):
    products: List[Dict[str, Any]]
    shelf: Optional[Dict[str, Any]] = None


@router.post("/score-planogram")
def score_planogram(req: PlanogramScoreRequest):
    return score_planogram_intelligence(req.planogram)


@router.post("/product-confidence")
def product_confidence(req: ProductConfidenceRequest):
    return product_placement_confidence(
        req.product,
        aisle=req.aisle,
        module=req.module,
        shelf=req.shelf,
        existing_products=req.existing_products,
    )


@router.post("/resolve-fixture-target")
def fixture_target(payload: Dict[str, Any] = Body(...)):
    product = payload.get("product") or payload
    return resolve_fixture_target(product)


@router.post("/compare-shelf-change")
def compare_change(req: ShelfImpactRequest):
    return compare_shelf_change(
        shelf=req.shelf,
        current_product=req.current_product,
        candidate_product=req.candidate_product,
        aisle=req.aisle,
        module=req.module,
    )


@router.post("/sort-suggestions")
def sort_suggestions(req: SuggestionSortRequest):
    return {
        "status": "success",
        "products": sort_suggestions_by_confidence(req.products, req.shelf),
    }


@router.post("/ollama-review")
def ollama_review(payload: Dict[str, Any] = Body(...)):
    # Deliberately safe placeholder: no hard dependency, no fake AI answer.
    # The deterministic score must exist before a local LLM explains it.
    score = payload.get("score") or payload.get("planogram_score") or payload
    return {
        "status": "not_configured",
        "message": "Ollama bağlantısı henüz aktif değil. Önce deterministic score/diagnostics hesaplandıktan sonra bu endpoint local model açıklaması üretmek için kullanılacak.",
        "expected_input": {
            "store_code": "FULYA",
            "planogram_score": 63,
            "ai_confidence_score": 61,
            "score_breakdown": {},
            "violations": [],
            "unplaced_products": [],
        },
        "received": score,
    }
