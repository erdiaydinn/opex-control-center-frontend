from fastapi import APIRouter, Header, HTTPException, Request

from app.modules.workforce.authorization import is_action_allowed
from .schemas import DecisionCreate, DocumentCreate, LocationLockCreate, ScanCreate
from .service import InventoryRuleError, complete, create_document, decide, get_document, initialize, list_documents, list_terminal_tasks, lock_location, readiness, record_scan

router = APIRouter(prefix="/inventory", tags=["Inventory V22"])

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


def run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except InventoryRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/health")
def health():
    return readiness()


@router.get("/documents")
def documents(request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "viewInventory")
    return {"rows": list_documents(scope(request))}


@router.get("/terminal/tasks")
def terminal_tasks(request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "viewInventory")
    return {"rows": list_terminal_tasks(scope(request))}


@router.post("/documents", status_code=201)
def add_document(payload: DocumentCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "createInventory")
    return run(create_document, payload.model_dump(), actor(request), scope(request))


@router.get("/documents/{document_id}")
def document(document_id: str, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "viewInventory")
    return run(get_document, document_id, scope(request))


@router.post("/documents/{document_id}/locations/{location}/lock")
def lock(document_id: str, location: str, payload: LocationLockCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "countInventory")
    return run(lock_location, document_id, location, payload.device_id, actor(request), payload.ttl_seconds, scope(request))


@router.post("/documents/{document_id}/scans")
def scan(document_id: str, payload: ScanCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "countInventory")
    return run(record_scan, document_id, payload.model_dump(), actor(request), scope(request))


@router.post("/documents/{document_id}/complete")
def close(document_id: str, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "completeInventory")
    return run(complete, document_id, actor(request), scope(request))


@router.post("/documents/{document_id}/decision")
def decision(document_id: str, payload: DecisionCreate, request: Request, x_opex_role: str = Header("viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header("", alias="X-OPEX-Permissions")):
    require(x_opex_role, x_opex_permissions, "approveInventory")
    return run(decide, document_id, payload.decision, payload.note, actor(request), scope(request))
