from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .model_promotion_gate import ModelPromotionGate, PromotionRecord, PromotionRequest

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
promotion_gate = ModelPromotionGate(DB_PATH)
router = APIRouter(prefix="/v1/model-promotions", tags=["model-promotions"])


@router.post("", response_model=PromotionRecord, status_code=201)
def promote_model(payload: PromotionRequest) -> PromotionRecord:
    """Perform the one canonical evidence-bound production transition."""

    try:
        return promotion_gate.promote(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{model_record_id}", response_model=PromotionRecord)
def get_current_production_promotion(model_record_id: str) -> PromotionRecord:
    """Re-verify and return the current immutable production proof."""

    try:
        return promotion_gate.require_current_production(model_record_id=model_record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
