from fastapi import APIRouter, Header, HTTPException, Request

from .operational_mobile_router import router as operational_mobile_router
from .recovery import (
    disposition_recovery_case,
    list_open_recovery_cases,
    request_recovery_case,
)
from .router import production_mode, production_principal, require_verified_identity, run
from .schemas import RecoveryCaseCreate, RecoveryDispositionCreate

router = APIRouter(prefix="/inventory", tags=["Inventory Recovery"])


@router.post("/v1/recovery-cases", status_code=201)
def create_recovery_case(
    payload: RecoveryCaseCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production recovery endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    return run(
        request_recovery_case,
        production_principal(request, x_eay_device_id),
        payload.model_dump(),
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )


@router.get("/v1/recovery-cases")
def open_recovery_cases(
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production recovery endpoint etkin değil.")
    require_verified_identity(request, "approveInventory")
    return {
        "rows": run(
            list_open_recovery_cases,
            production_principal(request, x_eay_device_id),
        )
    }


@router.post("/v1/recovery-cases/{case_id}/disposition")
def disposition_recovery(
    case_id: str,
    payload: RecoveryDispositionCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production recovery endpoint etkin değil.")
    require_verified_identity(request, "approveInventory")
    return run(
        disposition_recovery_case,
        production_principal(request, x_eay_device_id),
        case_id,
        payload.decision,
        payload.reason,
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )


router.include_router(operational_mobile_router)
