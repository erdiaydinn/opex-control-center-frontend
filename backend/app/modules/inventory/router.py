import os
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from app.modules.workforce.active_shift import ActiveShiftAuthorityError, resolve_active_shift
from app.modules.workforce.authorization import is_action_allowed
from .device_recovery import replace_managed_device
from .explanation import explanation_context
from .location_completion import (
    completion_readiness,
    filter_completed_terminal_tasks,
    record_location_completion,
)
from .mission_event import record_event as mission_record_event
from .mission_lease import (
    claim_terminal_mission,
    filter_and_annotate_terminal_tasks,
    lease_readiness,
    supersede_attempt,
)
from .production import (
    InventoryPrincipal,
    create_document as production_create_document,
    enroll_device,
    list_terminal_tasks as production_list_terminal_tasks,
    readiness as production_readiness,
    transition as production_transition,
)
from .reconciliation import reconciliation as read_reconciliation
from .operational_mission import create_operational_mission, claim_operational_mission, record_operational_event
from .schemas import (
    DecisionCreate,
    DeviceEnrollCreate,
    DeviceReplaceCreate,
    DocumentCreate,
    DocumentTransitionCreate,
    LocationCompletionCreate,
    LocationLockCreate,
    ScanCreate,
    TerminalEventCreate,
    TerminalMissionClaimCreate,
    TerminalMissionReassignCreate,
    OperationalMissionCreate,
    OperationalEventCreate,
)
from .service import (
    InventoryRuleError,
    complete,
    create_document,
    decide,
    get_document,
    initialize,
    list_documents,
    list_terminal_tasks,
    lock_location,
    readiness,
    record_scan,
)

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


def require_verified_identity(request: Request, action: str) -> None:
    """Authorize production operations only from middleware-verified identity state.

    Production middleware already strips inbound X-OPEX identity/permission headers.
    Keeping those headers out of the v1 route signature prevents future middleware or
    proxy refactors from accidentally turning a compatibility field into authority.
    """
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=401, detail="Doğrulanmış kurumsal kimlik gerekli.")

    roles = tuple(str(role) for role in (getattr(identity, "roles", ()) or ()) if str(role).strip())
    permissions = tuple(
        str(permission)
        for permission in (getattr(identity, "permissions", ()) or ())
        if str(permission).strip()
    )
    primary_role = str(getattr(identity, "primary_role", "") or (roles[0] if roles else "viewer"))
    require(primary_role, ",".join(permissions), action)


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


def active_shift_principal(principal: InventoryPrincipal) -> tuple[InventoryPrincipal, str] | None:
    """Narrow terminal scope to the one durable Workforce shift currently checked in."""
    try:
        attestation = resolve_active_shift(
            principal.tenant_id,
            principal.employee_id,
            principal.warehouse_scope,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ActiveShiftAuthorityError as error:
        raise HTTPException(
            status_code=503,
            detail="Workforce aktif vardiya doğrulaması geçici olarak kullanılamıyor.",
        ) from error
    if attestation is None:
        return None
    canonical_warehouse = next(
        (
            warehouse
            for warehouse in principal.warehouse_scope
            if str(warehouse).strip().lower() == str(attestation.warehouse_id).strip().lower()
        ),
        None,
    )
    if canonical_warehouse is None:
        raise HTTPException(
            status_code=403,
            detail="Aktif vardiya deposu doğrulanmış OIDC depo kapsamıyla eşleşmiyor.",
        )
    narrowed = InventoryPrincipal(
        tenant_id=principal.tenant_id,
        subject=principal.subject,
        employee_id=principal.employee_id,
        warehouse_scope=frozenset({canonical_warehouse}),
        device_id=principal.device_id,
    )
    return narrowed, attestation.shift_id


def run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except InventoryRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        if isinstance(error.__cause__, ActiveShiftAuthorityError):
            raise HTTPException(
                status_code=503,
                detail="Workforce event vardiya doğrulaması geçici olarak kullanılamıyor.",
            ) from error
        raise


def production_health() -> dict:
    result = production_readiness()
    checks = dict(result.get("checks", {}))
    checks["migration_v4_location_completion"] = completion_readiness()
    checks["migration_v5_mission_lease"] = lease_readiness()
    if checks.get("postgres_configured"):
        try:
            from .production import connect
            with connect() as db:
                checks["migration_v7_operational_missions"] = bool(db.execute("SELECT 1 FROM inventory_schema_migrations WHERE version=7").fetchone())
        except Exception:
            checks["migration_v7_operational_missions"] = False
    else:
        checks["migration_v7_operational_missions"] = False
    return {
        "status": "ready" if result.get("status") == "ready" and all(checks.values()) else "blocked",
        "checks": checks,
    }


@router.get("/health")
def health():
    return production_health() if production_mode() else readiness()


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
    require_verified_identity(request, "countInventory")
    principal = production_principal(request, x_eay_device_id)
    return run(
        mission_record_event,
        principal,
        payload.model_dump(),
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )


@router.post("/v1/terminal/location-completions")
def terminal_location_completion(
    payload: LocationCompletionCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production terminal endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    principal = production_principal(request, x_eay_device_id)
    return run(
        record_location_completion,
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


@router.post("/v1/devices/replace", status_code=201)
def device_replace(
    payload: DeviceReplaceCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production device replacement endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    return run(
        replace_managed_device,
        production_principal(request, x_eay_device_id),
        payload.replaced_device_id,
        payload.activation_code,
        payload.public_key_pem,
    )


@router.post("/v1/documents", status_code=201)
def create_production_document(
    payload: DocumentCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production document endpoint etkin değil.")
    require_verified_identity(request, "createInventory")
    return run(production_create_document, production_principal(request, x_eay_device_id), payload.model_dump())


@router.get("/v1/terminal/tasks")
def production_terminal_tasks(
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production terminal endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    principal = production_principal(request, x_eay_device_id)
    active = active_shift_principal(principal)
    if active is None:
        return {"rows": []}
    narrowed_principal, active_shift_id = active
    rows = run(production_list_terminal_tasks, narrowed_principal)
    rows = run(filter_completed_terminal_tasks, narrowed_principal, rows)
    rows = run(
        filter_and_annotate_terminal_tasks,
        narrowed_principal,
        active_shift_id,
        rows,
    )
    return {
        "rows": [
            {**row, "active_shift_id": active_shift_id}
            for row in rows
        ]
    }


@router.post("/v1/terminal/missions/claim")
def production_terminal_mission_claim(
    payload: TerminalMissionClaimCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
    x_eay_request_timestamp: str = Header(..., alias="X-EAY-Request-Timestamp"),
    x_eay_request_nonce: str = Header(..., alias="X-EAY-Request-Nonce"),
    x_eay_device_signature: str = Header(..., alias="X-EAY-Device-Signature"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production terminal endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    principal = production_principal(request, x_eay_device_id)
    active = active_shift_principal(principal)
    if active is None:
        raise HTTPException(status_code=409, detail="Aktif vardiya olmadan mission claim edilemez.")
    narrowed_principal, active_shift_id = active
    return run(
        claim_terminal_mission,
        narrowed_principal,
        active_shift_id,
        payload.model_dump(),
        x_eay_request_timestamp,
        x_eay_request_nonce,
        x_eay_device_signature,
    )


@router.post("/v1/documents/{document_id}/locations/{location_id}/reassign")
def production_terminal_mission_reassign(
    document_id: str,
    location_id: str,
    payload: TerminalMissionReassignCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production document endpoint etkin değil.")
    require_verified_identity(request, "approveInventory")
    try:
        parsed_document_id = UUID(document_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli document UUID zorunludur.") from error
    return run(
        supersede_attempt,
        production_principal(request, x_eay_device_id),
        parsed_document_id,
        location_id,
        payload.reason,
    )


@router.get("/v1/documents/{document_id}/reconciliation")
def production_reconciliation(
    document_id: str,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production reconciliation endpoint etkin değil.")
    require_verified_identity(request, "approveInventory")
    try:
        parsed = UUID(document_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli document UUID zorunludur.") from error
    return run(read_reconciliation, production_principal(request, x_eay_device_id), parsed)


@router.get("/v1/documents/{document_id}/explanation-context")
def production_explanation_context(
    document_id: str,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production explanation endpoint etkin değil.")
    require_verified_identity(request, "approveInventory")
    try:
        parsed_document_id = UUID(document_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Geçerli document UUID zorunludur.") from error
    return run(
        explanation_context,
        production_principal(request, x_eay_device_id),
        parsed_document_id,
    )


@router.post("/v1/documents/{document_id}/transition")
def transition_document(
    document_id: str,
    payload: DocumentTransitionCreate,
    request: Request,
    x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID"),
):
    if not production_mode():
        raise HTTPException(status_code=404, detail="Production document endpoint etkin değil.")
    require_verified_identity(
        request,
        "approveInventory" if payload.target_state in {"APPROVED", "LOCKED", "REJECTED"} else "completeInventory",
    )
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

@router.post("/v1/operational-missions", status_code=201)
def create_operation(payload: OperationalMissionCreate, request: Request, x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID")):
    if not production_mode(): raise HTTPException(status_code=404, detail="Production operational endpoint etkin değil.")
    require_verified_identity(request, "createInventory")
    return run(create_operational_mission, production_principal(request, x_eay_device_id), payload.model_dump())

@router.post("/v1/operational-missions/{mission_id}/claim")
def claim_operation(mission_id: str, request: Request, x_eay_device_id: str = Header(..., alias="X-EAY-Device-ID")):
    if not production_mode(): raise HTTPException(status_code=404, detail="Production operational endpoint etkin değil.")
    require_verified_identity(request, "countInventory")
    principal=production_principal(request,x_eay_device_id); active=active_shift_principal(principal)
    if active is None: raise HTTPException(status_code=409,detail="Aktif vardiya olmadan mission claim edilemez.")
    narrowed,shift_id=active
    try: parsed=UUID(mission_id)
    except ValueError as error: raise HTTPException(status_code=400,detail="Geçerli mission UUID zorunludur.") from error
    return run(claim_operational_mission,narrowed,parsed,shift_id)

@router.post("/v1/operational-events")
def operational_event(payload: OperationalEventCreate, request: Request, x_eay_device_id: str = Header(...,alias="X-EAY-Device-ID"), x_eay_request_timestamp: str = Header(...,alias="X-EAY-Request-Timestamp"), x_eay_request_nonce: str = Header(...,alias="X-EAY-Request-Nonce"), x_eay_device_signature: str = Header(...,alias="X-EAY-Device-Signature")):
    if not production_mode(): raise HTTPException(status_code=404, detail="Production operational endpoint etkin değil.")
    require_verified_identity(request,"countInventory")
    return run(record_operational_event,production_principal(request,x_eay_device_id),payload.model_dump(),x_eay_request_timestamp,x_eay_request_nonce,x_eay_device_signature)
