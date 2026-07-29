from fastapi import APIRouter, Body
from engines.capacity_engine import score_capacity
from engines.route_engine import route_score

router = APIRouter(prefix="/core/intelligence", tags=["core-intelligence"])

@router.post("/capacity")
def capacity(payload: dict = Body(...)):
    layout = payload.get("layout") or payload
    dna = payload.get("dna")
    return {"success": True, "capacity": score_capacity(layout, dna)}

@router.post("/route")
def route(payload: dict = Body(...)):
    layout = payload.get("layout") or payload
    sequence = payload.get("sequence")
    return {"success": True, "route": route_score(layout, sequence)}
