
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List
from services.ai_council import review_planogram

router = APIRouter(prefix="/ai/council", tags=["ai-council"])

class CouncilRequest(BaseModel):
    products: List[Dict[str, Any]] = []
    layout: Dict[str, Any] = {}
    planogram: Dict[str, Any] = {}

@router.post("/review")
def review(req: CouncilRequest):
    return review_planogram(req.model_dump())
