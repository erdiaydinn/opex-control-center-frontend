from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .model_promotion_gate import ModelPromotionGate, PromotionRecord, PromotionRequest

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
promotion_gate = ModelPromotionGate(DB_PATH)
class PromotionApiRequest(BaseModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    canary_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_evaluation_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_reference: str = Field(min_length=2, max_length=300)


def _authorized_release_operator(authorization: str | None) -> str:
    expected_token = os.getenv("EAY_MODEL_PROMOTION_API_TOKEN", "")
    operator = os.getenv("EAY_MODEL_PROMOTION_OPERATOR_ID", "").strip()
    if len(expected_token) < 32 or len(operator) < 2:
        raise HTTPException(status_code=503, detail="model_promotion_api_not_configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="model_promotion_authorization_required")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="model_promotion_authorization_invalid")
    return operator


def promote_model(
    payload: PromotionApiRequest,
    authorization: str | None = None,
) -> PromotionRecord:
    """Perform the one canonical evidence-bound production transition.

    The release approver identity is deployment-authoritative and cannot be
    supplied by the request body. The endpoint is disabled unless both the
    operator identity and a strong bearer secret are explicitly configured.
    """

    approved_by = _authorized_release_operator(authorization)
    request = PromotionRequest(
        model_record_id=payload.model_record_id,
        canary_evidence_fingerprint=payload.canary_evidence_fingerprint,
        release_evaluation_evidence_fingerprint=payload.release_evaluation_evidence_fingerprint,
        approved_by=approved_by,
        approval_reference=payload.approval_reference,
    )
    try:
        return promotion_gate.promote(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_current_production_promotion(model_record_id: str) -> PromotionRecord:
    """Re-verify and return the current immutable production proof."""

    try:
        return promotion_gate.require_current_production(model_record_id=model_record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
