import os
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from app.modules.workforce.authorization import is_action_allowed
from .schemas import DecisionCreate, DeviceEnrollCreate, DocumentCreate, DocumentTransitionCreate, LocationLockCreate, ScanCreate, TerminalEventCreate
from .production import InventoryPrincipal, create_document as production_create_document, enroll_device, list_terminal_tasks as production_list_terminal_tasks, readiness as production_readiness, reconciliation, record_event as production_record_event, transition as production_transition
from .service import InventoryRuleError, complete, create_document, decide, get_document, initialize, list_documents, list_terminal_tasks, lock_location, readiness, record_scan

router = APIRouter(prefix="/inventory", tags=["Inventory V22"])


def production_mode() -> bool:
    return os.getenv("EAY_INVENTORY_MODE", "pilot").lower() == "production"


def require_pilot_mode() -> None:
    if production_mode():
        raise HTTPException(status_code=410, detail="Legacy Inventory endpoint production ortamında kapalıdır.")

ROLE_ACTIONS = {
    "counter": {"viewInventory", "countInventory"},
    "warehouse_manager": {"viewInventory", "countInventory", "completeInventory", "approveInventory"},
    "regional_manager": {"viewInventory", "approveInventory"},
    "inventory_control": {"viewInventory", "createInventory", "completeInventory", "approveInventory"},
    "auditor": {"viewInventory", "viewInventoryAudit"},
}


def require(role: str, permissions: str, action: str) -> None:
    normalized = role.strip().lower().replace("-", "_").replace(" ", "_")
    if action in ROLE_ACTIONS.get(normalized, set()) or is_action_allowed(role, permissions, action):
        return
    raise HTTPException(status_code=403, detail=f"Bu işlem için {action} yetkisi gerekir.")


def actor(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    return getattr(identity, "subject", "unknown")


def scope(request: Request) -> set[str] | None:
    identity = getattr(request.state, "identity", None)
    values = getattr(identity, "warehouse_scope", None)
    return set(values) if values else None


def production_principal(request: Request, device_id: str) -> InventoryPrincipal:
    identity = getattr(request.state, "identity", None)
    try:
        return InventoryPrincipal(
            tenant_id=getattr(identity, "tenant_id", ""),
            subject=getattr(identity, "subject", ""),
            employee_id=getattr(identity, "employee_id", "") or "",
            warehouse_scope=frozenset(getattr(identity, "warehouse_scope", ()) or ()),
            device_id=UUID(device_id),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli managed device UUID zorunludur.") from error


def run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except InventoryRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/health")
def health():
    return production_readiness() if production_mode() else readiness()


@router.get("/documents")
def documents(request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "viewInventory")
    return {"rows": list_documents(scope(request))}


@router.get("/terminal/tasks")
def terminal_tasks(request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "viewInventory")
    return {"rows": list_terminal_tasks(scope(request))}


@router.post("/documents", status_code=201)
def add_document(payload: DocumentCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "createInventory")
    return run(create_document, payload.model_dump(), actor(request), scope(request))


@router.get("/documents/{document_id}")
def document(document_id: str, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "viewInventory")
    return run(get_document, document_id, scope(request))


@router.post("/documents/{document_id}/locations/{location}/lock")
def lock(document_id: str, location: str, payload: LocationLockCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "countInventory")
    return run(lock_location, document_id, location, payload.device_id, actor(request), payload.ttl_seconds, scope(request))


@router.post("/documents/{document_id}/scans")
def scan(document_id: str, payload: ScanCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "countInventory")
    return run(record_scan, document_id, payload.model_dump(), actor(request), scope(request))


@router.post("/documents/{document_id}/complete")
def close(document_id: str, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "completeInventory")
    return run(complete, document_id, actor(request), scope(request))


@router.post("/documents/{document_id}/decision")
def decision(document_id: str, payload: DecisionCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require_pilot_mode()
    require(x_opex_role, x_opex_permissions, "approveInventory")
    return run(decide, document_id, payload.decision, payload.note, actor(request), scope(request))


@router.post("/v1/terminal/events")
def terminal_event(
    payload: TerminalEventCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production terminal endpoint etkin değil.")
    principal = production_principal(request, x_eay_device_id)
    return run(
        production_record_event,
        principal,
        payload.model_dump(),
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )


@router.post("/v1/devices/enroll", status_code=201)
def device_enroll(
    payload: DeviceEnrollCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production enrollment endpoint etkin değil.")
    return run(
        enroll_device,
        production_principal(request, x_eay_device_id),
        payload.activation_code,
        payload.public_key_pem,
    )


@router.post("/v1/documents", status_code=201)
def create_production_document(
    payload: DocumentCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_opex_role: str = Header("viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header("", alias="X-OPEX-Permissions"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production document endpoint etkin değil.")
    require(x_opex_role, x_opex_permissions, "createInventory")
    return run(production_create_document, production_principal(request, x_eay_device_id), payload.model_dump())


@router.get("/v1/terminal/tasks")
def production_terminal_tasks(
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production terminal endpoint etkin değil.")
    return {"rows": run(production_list_terminal_tasks, production_principal(request, x_eay_device_id))}


@router.get("/v1/documents/{document_id}/reconciliation")
def production_reconciliation(
    document_id: str,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_opex_role: str = Header("viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header("", alias="X-OPEX-Permissions"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production reconciliation endpoint etkin değil.")
    require(x_opex_role, x_opex_permissions, "approveInventory")
    try:
        parsed = UUID(document_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli document UUID zorunludur.") from error
    return run(reconciliation, production_principal(request, x_eay_device_id), parsed)


@router.post("/v1/documents/{document_id}/transition")
def transition_document(
    document_id: str,
    payload: DocumentTransitionCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_opex_role: str = Header("viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header("", alias="X-OPEX-Permissions"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production document endpoint etkin değil.")
    require(x_opex_role, x_opex_permissions, "approveInventory" if payload.target_state in {"APPROVED", "LOCKED", "REJECTED"} else "completeInventory")
    try:
        parsed_document_id = UUID(document_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli document UUID zorunludur.") from error
    return run(
        production_transition,
        production_principal(request, x_eay_device_id),
        parsed_document_id,
        payload.expected_revision,
        payload.target_state,
        payload.reason,
    )
