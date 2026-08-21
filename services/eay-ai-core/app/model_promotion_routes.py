from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .model_promotion_gate import ModelPromotionGate, PromotionRecord, PromotionRequest

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
promotion_gate = ModelPromotionGate(DB_PATH)
MODEL_PROOF_TTL_SECONDS = 30


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


class ProductionModelProofEnvelope(BaseModel):
    model_record_id: str
    artifact_sha256: str
    artifact_provenance_fingerprint: str
    production_promotion_fingerprint: str
    production_release_proof_fingerprint: str
    challenge: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: datetime
    expires_at: datetime
    seal: str = Field(pattern=r"^[0-9a-f]{64}$")


def _model_proof_token(authorization: str | None) -> str:
    expected = os.getenv("EAY_MODEL_PROOF_API_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="model_proof_api_not_configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="model_proof_authorization_required")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="model_proof_authorization_invalid")
    return expected


def _proof_payload(envelope: dict[str, object]) -> bytes:
    return json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def issue_current_production_model_proof(
    model_record_id: str,
    *,
    challenge: str,
    authorization: str | None,
) -> ProductionModelProofEnvelope:
    """Re-verify AI lifecycle authority and seal one fresh caller challenge."""

    if len(challenge) != 64 or any(char not in "0123456789abcdef" for char in challenge):
        raise HTTPException(status_code=400, detail="model_proof_challenge_invalid")
    token = _model_proof_token(authorization)
    promotion = get_current_production_promotion(model_record_id)
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=MODEL_PROOF_TTL_SECONDS)
    payload: dict[str, object] = {
        "model_record_id": promotion.model_record_id,
        "artifact_sha256": promotion.artifact_sha256,
        "artifact_provenance_fingerprint": promotion.artifact_provenance_fingerprint,
        "production_promotion_fingerprint": promotion.fingerprint,
        "production_release_proof_fingerprint": promotion.release_proof_fingerprint,
        "challenge": challenge,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    seal = hmac.new(token.encode("utf-8"), _proof_payload(payload), hashlib.sha256).hexdigest()
    return ProductionModelProofEnvelope(**payload, seal=seal)
