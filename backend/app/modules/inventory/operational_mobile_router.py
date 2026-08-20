from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .operational_claim import claim_operational_mission_signed
from .operational_mission import record_operational_event
from .operational_mobile import list_operational_mobile_missions
from .operational_recovery import release_operational_claim
from .router import (
    active_shift_principal,
    production_mode,
    production_principal,
    require_verified_identity,
    run,
)
from .schemas import OperationalEventCreate

router = APIRouter(prefix="/v1/mobile", tags=["Inventory Mobile Operations"])


class OperationalClaimReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


def _operational_event_response(
    result: dict,
    active_shift_id: str,
    claim_id: str,
) -> dict:
    """Preserve authoritative replay semantics in the mobile ACK contract."""
    return {
        **result,
        "accepted": result.get("code") == "ACCEPTED",
        "active_shift_id": active_shift_id,
        "claim_id": claim_id,
        "idempotent_replay": bool(result.get("idempotent_replay", False)),
    }


@router.get("/operational-missions")
def mobile_operational_missions(
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production operational mobile endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    principal = production_principal(request, x_eay_device_id)
    active = active_shift_principal(principal)
    if active is None:
        return {"rows": []}
    narrowed, active_shift_id = active
    rows = run(list_operational_mobile_missions, narrowed, active_shift_id)
    return {
        "rows": [
            {**row, "active_shift_id": active_shift_id}
            for row in rows
        ]
    }


@router.post("/operational-missions/{mission_id}/claim")
def mobile_operational_claim(
    mission_id: str,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production operational mobile endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    principal = production_principal(request, x_eay_device_id)
    active = active_shift_principal(principal)
    if active is None:
        raise HTTPException(status_code=409, detail="Aktif vardiya olmadan mission claim edilemez.")
    narrowed, active_shift_id = active
    try:
        parsed = UUID(mission_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli mission UUID zorunludur.") from error
    result = run(
        claim_operational_mission_signed,
        narrowed,
        parsed,
        active_shift_id,
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )
    return {**result, "active_shift_id": active_shift_id}


@router.post("/operational-missions/{mission_id}/release")
def mobile_operational_claim_release(
    mission_id: str,
    payload: OperationalClaimReleaseCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production operational mobile endpoint etkin değil.")
    require_verified_identity(request, "completeInventory")
    try:
        parsed = UUID(mission_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli mission UUID zorunludur.") from error
    return run(
        release_operational_claim,
        production_principal(request, x_eay_device_id),
        parsed,
        payload.reason,
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )


@router.post("/operational-events")
def mobile_operational_event(
    payload: OperationalEventCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production operational mobile endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    result = run(
        record_operational_event,
        production_principal(request, x_eay_device_id),
        payload.model_dump(),
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )
    return _operational_event_response(
        result,
        payload.active_shift_id,
        payload.claim_id,
    )
