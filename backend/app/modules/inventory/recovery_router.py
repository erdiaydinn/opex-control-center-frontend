from fastapi import APIRouter, Header, HTTPException, Request

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
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production recovery endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    return run(
        request_recovery_case,
        production_principal(request, x_eay_device_id),
        payload.model_dump(),
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
    )
