from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .legal_engine import (
    ConflictFinding,
    LegalEngine,
    LegalInstrumentUpsert,
    LegalRequirementUpsert,
)
from .legal_temporal import LegalTemporalResolver
from .legal_temporal_conflicts import TemporalConflictEngine, TemporalResolutionBlocked


DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
engine = LegalEngine(DB_PATH)
temporal_resolver = LegalTemporalResolver(DB_PATH)
temporal_conflicts = TemporalConflictEngine(DB_PATH)
router = APIRouter(prefix="/v1/legal", tags=["legal"])


@router.post("/instruments", status_code=204)
def upsert_instrument(item: LegalInstrumentUpsert):
    engine.upsert_instrument(item)
    return None


@router.get("/instruments")
def list_instruments(as_of: date = Query(default_factory=date.today)):
    return engine.instruments_as_of(as_of)


@router.get("/temporal-state")
def temporal_state(as_of: date = Query(default_factory=date.today)):
    """Return fail-closed historical legal graph state for the requested date."""
    state = temporal_resolver.resolve(as_of)
    if not state.resolved:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "legal_temporal_resolution_blocked",
                "as_of": state.as_of,
                "blockers": list(state.blockers),
                "resolution_fingerprint": state.resolution_fingerprint,
            },
        )
    return state.as_dict()


@router.post("/requirements", status_code=204)
def upsert_requirement(item: LegalRequirementUpsert):
    try:
        engine.upsert_requirement(item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return None


@router.get("/conflicts", response_model=list[ConflictFinding])
def company_vs_law(as_of: date = Query(default_factory=date.today)):
    try:
        findings, _resolution_fingerprint = temporal_conflicts.compare_company_to_law(as_of)
        return findings
    except TemporalResolutionBlocked as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "legal_temporal_resolution_blocked",
                "as_of": as_of.isoformat(),
                "blockers": list(exc.blockers),
                "resolution_fingerprint": exc.resolution_fingerprint,
            },
        ) from exc
