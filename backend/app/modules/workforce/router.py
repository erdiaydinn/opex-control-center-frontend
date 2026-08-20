import os
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, status

from .authorization import is_action_allowed
from .schemas import (
    ApprovalRequest,
    AnnouncementCreateRequest,
    AnnouncementReceiptRequest,
    AttendanceImportRequest,
    BulkApprovalRequest,
    BreakActionRequest,
    CheckInRequest,
    CheckOutRequest,
    DeviceChallengeRequest,
    DeviceRegisterRequest,
    DeviceResetRequest,
    FeatureFlagsUpdateRequest,
    EmploymentLifecycleImportRequest,
    LeaveImportRequest,
    LeaveRequestCreateRequest,
    LeaveRequestResolveRequest,
    ManualCorrectionRequest,
    ManagerTaskResolveRequest,
    NotificationPolicyUpdateRequest,
    PeopleBulkUpsertRequest,
    WarehouseBulkPatchRequest,
    WarehouseUpsertRequest,
    PickerCorrectionCreateRequest,
    RuleVersionCreateRequest,
    ShiftCreateRequest,
)
from .service import (
    WorkforceRuleError,
    approve_attendance,
    bulk_approve_attendance,
    check_in,
    check_out,
    change_break,
    correct_attendance,
    create_announcement,
    dismiss_announcement,
    create_correction_request,
    create_leave_request,
    create_rule_version,
    create_shift,
    get_notification_policy,
    get_feature_flags,
    list_audit,
    list_attendance,
    list_daily_status,
    list_breaks,
    list_device_bindings,
    list_announcements,
    list_announcement_receipts,
    list_manager_tasks,
    list_notifications,
    list_leave_requests,
    list_leaves,
    list_rules,
    list_shifts,
    list_warehouses,
    list_people,
    register_device,
    resolve_manager_task,
    resolve_leave_request,
    reset_device_binding,
    update_notification_policy,
    update_feature_flags,
    upsert_people,
    update_employment_lifecycle,
    import_attendance,
    import_leaves,
    issue_device_challenge,
    upsert_warehouse,
    bulk_patch_warehouses,
    mark_notification_read,
    delete_notification,
    clear_notifications,
)


router = APIRouter(prefix="/workforce", tags=["Workforce"])


def _require(role: str, permissions: str, action: str) -> None:
    if not is_action_allowed(role, permissions, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bu işlem için {action} yetkisi gerekir.",
        )


def _require_any(role: str, permissions: str, *actions: str) -> None:
    if any(is_action_allowed(role, permissions, action) for action in actions):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Bu işlem için şu yetkilerden biri gerekir: {', '.join(actions)}.")


def _normalized_role(role: str) -> str:
    return role.strip().lower().replace("-", "_").replace(" ", "_")


def _warehouse_key(value: object) -> str:
    return str(value or "").strip().casefold().translate(str.maketrans("üıöşçğ", "uioscg"))


def _canonical_warehouse_id(value: object) -> str | None:
    key = _warehouse_key(value)
    if not key:
        return None
    warehouses = list_warehouses()
    exact = next((row for row in warehouses if key in {_warehouse_key(row.get("id")), _warehouse_key(row.get("name"))}), None)
    if exact:
        return _warehouse_key(exact["id"])
    aliases = [row for row in warehouses if _warehouse_key(row.get("name")).startswith(f"{key} (")]
    return _warehouse_key(aliases[0]["id"]) if len(aliases) == 1 else None


def _identity_employee_id(request: Request) -> str | None:
    identity = getattr(request.state, "identity", None)
    value = getattr(identity, "employee_id", None)
    return str(value) if value not in (None, "") else None


def _employee_warehouse_id(employee_id: str | None) -> str | None:
    if not employee_id:
        return None
    person = next(
        (
            item for item in list_people(False)
            if str(item.get("id") or item.get("employee_id")) == str(employee_id)
        ),
        None,
    )
    return _canonical_warehouse_id((person or {}).get("warehouse_id") or (person or {}).get("warehouse"))


def _warehouse_scope(request: Request, role: str) -> set[str] | None:
    """Return verified warehouse scope; employee identities are own-site only.

    Global admin/HR identities retain tenant scope. Regional/warehouse roles use
    the signed warehouse_scope claim. Employee/picker roles are resolved through
    canonical Employee Master and never receive tenant-wide location scope in
    production. Development keeps legacy demo compatibility only when authority
    claims are absent.
    """
    normalized_role = _normalized_role(role)
    if normalized_role in {"super_admin", "superadmin", "admin", "administrator", "hr"}:
        return None
    identity = getattr(request.state, "identity", None)
    scope = {
        canonical
        for value in getattr(identity, "warehouse_scope", ())
        if (canonical := _canonical_warehouse_id(value)) is not None
    }
    if scope:
        return scope
    if normalized_role in {"picker", "employee", "worker"}:
        own_warehouse = _employee_warehouse_id(_identity_employee_id(request))
        if own_warehouse:
            return {own_warehouse}
        if os.getenv("DOCKOS_ENV", "development").lower() == "production":
            raise HTTPException(status_code=403, detail="Employee Master depo/store kapsamı gerekli.")
        return None
    if os.getenv("DOCKOS_ENV", "development").lower() == "production":
        raise HTTPException(status_code=403, detail="JWT warehouse_scope claim'i gerekli.")
    return None


def _require_global_scope(request: Request, role: str, action: str) -> None:
    if _warehouse_scope(request, role) is not None:
        raise HTTPException(
            status_code=403,
            detail=f"{action} tenant-geneli authority gerektirir; depo kapsamlı rol bu işlemi yapamaz.",
        )


def _row_warehouse_id(row: dict) -> str | None:
    direct = row.get("warehouse_id")
    if direct:
        return _canonical_warehouse_id(direct)
    if row.get("id") and row.get("latitude") is not None and row.get("longitude") is not None:
        return _canonical_warehouse_id(row["id"])
    shift_id = row.get("shift_id")
    if shift_id:
        shift = next((item for item in list_shifts() if item.get("id") == shift_id), None)
        if shift and shift.get("warehouse_id"):
            return _canonical_warehouse_id(shift["warehouse_id"])
    person_id = row.get("person_id") or row.get("employee_id")
    if person_id and person_id != "*":
        person = next((item for item in list_people(False) if item.get("id") == person_id or item.get("employee_id") == person_id), None)
        if person and (person.get("warehouse_id") or person.get("warehouse")):
            return _canonical_warehouse_id(person.get("warehouse_id") or person.get("warehouse"))
    warehouse = str(row.get("warehouse") or "").strip().lower()
    if warehouse:
        return _canonical_warehouse_id(warehouse)
    return None


def _scoped_rows(request: Request, role: str, rows: list[dict]) -> list[dict]:
    scope = _warehouse_scope(request, role)
    return rows if scope is None else [row for row in rows if _row_warehouse_id(row) in scope]


def _require_rows_in_scope(request: Request, role: str, rows: list[dict]) -> None:
    scope = _warehouse_scope(request, role)
    if scope is not None and any(_row_warehouse_id(row) not in scope for row in rows):
        raise HTTPException(status_code=403, detail="Kayıt yetkili depo kapsamınızın dışında.")


def _enforce_self(request: Request, person_id: str, role: str) -> None:
    from .service import person_has_workforce_access, resolve_person_identity

    person = resolve_person_identity(person_id, "EMPLOYEE_ID")
    if person is not None and not person_has_workforce_access(person):
        raise HTTPException(status_code=403, detail="İşten ayrılmış veya pasif personelin Workforce erişimi kapalıdır.")
    expected = _identity_employee_id(request)
    if expected:
        if str(expected) != str(person_id):
            raise HTTPException(status_code=403, detail="Yalnızca kendi Workforce kaydınıza erişebilirsiniz.")
        return
    # Privileged web/admin operations use their dedicated permission + scope
    # routes. Mobile/self-service presence actions never allow role-based
    # impersonation in production.
    if os.getenv("DOCKOS_ENV", "development").lower() != "production":
        return
    raise HTTPException(status_code=403, detail="JWT employee_id claim'i gerekli.")


def _scoped_person_id(request: Request, requested: str | None, role: str) -> str | None:
    if _normalized_role(role) in {"admin", "administrator", "super_admin", "superadmin", "manager", "warehouse_manager", "hr"}:
        return requested
    expected = _identity_employee_id(request)
    if expected:
        if requested and str(requested) != str(expected):
            raise HTTPException(status_code=403, detail="Başka personele ait kayıt görüntülenemez.")
        return expected
    if os.getenv("DOCKOS_ENV", "development").lower() == "production":
        raise HTTPException(status_code=403, detail="JWT employee_id claim'i gerekli.")
    return requested


def _announcement_is_published(row: dict) -> bool:
    if row.get("active") is False:
        return False
    raw = row.get("publish_at")
    if not raw:
        return True
    try:
        published_at = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        return published_at.astimezone(UTC) <= datetime.now(UTC)
    except (TypeError, ValueError):
        return False


def _announcement_target_warehouse(row: dict) -> str | None:
    target_type = str(row.get("target_type") or "all").strip().lower()
    target_value = str(row.get("target_value") or "").strip()
    if target_type == "warehouse":
        return _canonical_warehouse_id(target_value)
    if target_type == "person":
        return _employee_warehouse_id(target_value)
    return None


def _scoped_announcements(request: Request, role: str, rows: list[dict], person_id: str | None = None) -> list[dict]:
    published = [row for row in rows if _announcement_is_published(row)]
    if person_id:
        own_warehouse = _employee_warehouse_id(person_id)
        return [
            row for row in published
            if str(row.get("target_type") or "all").strip().lower() == "all"
            or (
                str(row.get("target_type") or "").strip().lower() == "person"
                and str(row.get("target_value") or "") == str(person_id)
            )
            or (
                str(row.get("target_type") or "").strip().lower() == "warehouse"
                and own_warehouse is not None
                and _canonical_warehouse_id(row.get("target_value")) == own_warehouse
            )
        ]
    scope = _warehouse_scope(request, role)
    if scope is None:
        return published
    return [
        row for row in published
        if str(row.get("target_type") or "all").strip().lower() == "all"
        or _announcement_target_warehouse(row) in scope
    ]


def _require_announcement_target_scope(request: Request, role: str, payload: AnnouncementCreateRequest) -> None:
    scope = _warehouse_scope(request, role)
    if scope is None:
        return
    target_type = payload.target_type.strip().lower()
    target_value = payload.target_value.strip()
    if target_type == "all":
        raise HTTPException(status_code=403, detail="Depo kapsamlı rol tenant geneli duyuru yayınlayamaz.")
    if target_type == "warehouse":
        target = _canonical_warehouse_id(target_value)
        if target is None or target not in scope:
            raise HTTPException(status_code=403, detail="Duyuru hedefi yetkili depo kapsamınızın dışında.")
        return
    if target_type == "person":
        target = _employee_warehouse_id(target_value)
        if target is None or target not in scope:
            raise HTTPException(status_code=403, detail="Duyuru hedef personeli yetkili depo kapsamınızın dışında.")
        return
    raise HTTPException(status_code=400, detail="Duyuru hedef tipi geçersiz.")


@router.get("/health")
def health() -> dict:
    from .persistence import ENABLED, SCHEMA_VERSION, TENANT_ID, ready, schema_version
    production = os.getenv("DOCKOS_ENV", "development").lower() == "production"
    current_schema_version = schema_version() or 0
    controls = {
        "postgresql": ENABLED and ready(),
        "tenant_id": bool(TENANT_ID),
        "atomic_snapshot_audit": ENABLED and current_schema_version >= SCHEMA_VERSION,
        "oidc": bool(os.getenv("OPEX_OIDC_ISSUER") and os.getenv("OPEX_OIDC_AUDIENCE")),
        "oidc_employee_claim_mapping": bool(os.getenv("OPEX_OIDC_EMPLOYEE_ID_CLAIM")),
        "oidc_warehouse_claim_mapping": bool(os.getenv("OPEX_OIDC_WAREHOUSE_SCOPE_CLAIM")),
        "oidc_exit_revocation": bool(os.getenv("OPEX_OIDC_REVOCATION_URL") and os.getenv("OPEX_OIDC_REVOCATION_TOKEN")),
        "pii_encryption_key": bool(os.getenv("OPEX_PII_KEY")),
        "apple_app_attest": bool(os.getenv("APPLE_APP_ATTEST_VERIFY_URL")),
        "google_play_integrity": bool(os.getenv("GOOGLE_PLAY_INTEGRITY_VERIFY_URL")),
        "attestation_gateway_credentials": bool(os.getenv("OPEX_ATTESTATION_GATEWAY_TOKEN")),
        "local_user_presence_required": production or os.getenv("WORKFORCE_REQUIRE_LOCAL_AUTH", "false").lower() == "true",
        "continuous_location_tracking": False,
        "biometric_template_storage": False,
    }
    required = (
        "postgresql", "tenant_id", "atomic_snapshot_audit", "oidc",
        "oidc_employee_claim_mapping", "oidc_warehouse_claim_mapping", "oidc_exit_revocation",
        "pii_encryption_key", "apple_app_attest", "google_play_integrity",
        "attestation_gateway_credentials", "local_user_presence_required",
    )
    configured = all(controls[key] for key in required) if production else True
    return {
        "status": "ok" if ready() and configured else "degraded",
        "module": "workforce",
        "postgresql": ENABLED,
        "schema_version": current_schema_version,
        "required_schema_version": SCHEMA_VERSION,
        "manual_correction": "permission-guarded",
        "audit": "hash-chained-atomic",
        "persistence": "tenant-scoped-optimistic",
        "device_binding": "single-active-device",
        "push": "durable-outbox",
        "production_controls": controls,
    }


@router.get("/warehouses")
def warehouses(request: Request, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    return {"rows": _scoped_rows(request, x_opex_role, list_warehouses())}


@router.post("/warehouses")
def save_warehouse(payload: WarehouseUpsertRequest, request: Request, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageWarehouses")
    _require_rows_in_scope(request, x_opex_role, [payload.model_dump()])
    return upsert_warehouse(payload.model_dump(), x_opex_user)


@router.patch("/warehouses")
def patch_warehouses(payload: WarehouseBulkPatchRequest, request: Request, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageWarehouses")
    _require_rows_in_scope(request, x_opex_role, [{"warehouse_id": warehouse_id} for warehouse_id in payload.warehouse_ids])
    rows = bulk_patch_warehouses(payload.warehouse_ids, payload.model_dump(exclude={"warehouse_ids"}), x_opex_user)
    return {"updated": len(rows), "rows": rows}


@router.get("/mobile/bootstrap")
def mobile_bootstrap(
    request: Request,
    person_id: str,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, person_id, x_opex_role)
    own_shifts = list_shifts(person_id)
    shift_ids = {item["id"] for item in own_shifts}
    return {
        "person_id": person_id,
        "shifts": own_shifts,
        "attendance": [item for item in list_attendance() if item.get("person_id") == person_id],
        "breaks": list_breaks(person_id),
        "notifications": list_notifications(person_id),
        "leave_requests": list_leave_requests(person_id, None),
        "manager_tasks": [item for item in list_manager_tasks() if item.get("person_id") == person_id or item.get("assignee_id") == person_id],
        "correction_requests": [item for item in list_manager_tasks() if item.get("shift_id") in shift_ids],
        "announcements": _scoped_announcements(request, x_opex_role, list_announcements(), person_id),
        "announcement_receipts": list_announcement_receipts(person_id),
        "features": get_feature_flags(),
        "notification_policy": get_notification_policy(),
    }


@router.get("/admin/bootstrap")
def admin_bootstrap(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewWorkforce")
    sensitive = is_action_allowed(x_opex_role, x_opex_permissions, "viewSensitiveIdentity") or is_action_allowed(x_opex_role, x_opex_permissions, "viewFullNationalId")
    scope = _warehouse_scope(request, x_opex_role)
    return {
        "people": _scoped_rows(request, x_opex_role, list_people(sensitive)),
        "warehouses": _scoped_rows(request, x_opex_role, list_warehouses()),
        "rules": list_rules(),
        "shifts": _scoped_rows(request, x_opex_role, list_shifts()),
        "attendance": _scoped_rows(request, x_opex_role, list_attendance()),
        "leaves": _scoped_rows(request, x_opex_role, list_leaves()),
        "devices": _scoped_rows(request, x_opex_role, list_device_bindings()),
        "leave_requests": _scoped_rows(request, x_opex_role, list_leave_requests()),
        "manager_tasks": _scoped_rows(request, x_opex_role, list_manager_tasks()),
        "announcements": _scoped_announcements(request, x_opex_role, list_announcements()),
        "features": get_feature_flags(),
        "notification_policy": get_notification_policy(),
        "audit": list_audit(1000) if scope is None and is_action_allowed(x_opex_role, x_opex_permissions, "viewAuditLog") else [],
    }


@router.get("/people")
def people(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewPeople")
    sensitive = is_action_allowed(x_opex_role, x_opex_permissions, "viewSensitiveIdentity") or is_action_allowed(x_opex_role, x_opex_permissions, "viewFullNationalId")
    return {"rows": _scoped_rows(request, x_opex_role, list_people(sensitive))}


@router.post("/people/bulk-upsert")
def people_bulk_upsert(
    payload: PeopleBulkUpsertRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_any(x_opex_role, x_opex_permissions, "managePeople", "manageEmployees")
    _require_rows_in_scope(request, x_opex_role, [row.model_dump() for row in payload.rows])
    return upsert_people([row.model_dump() for row in payload.rows], x_opex_user)


@router.post("/people/employment-lifecycle/import")
def employment_lifecycle_import(
    payload: EmploymentLifecycleImportRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_any(x_opex_role, x_opex_permissions, "managePeople", "manageEmployees")
    _require_rows_in_scope(request, x_opex_role, [row.model_dump() for row in payload.rows])
    return update_employment_lifecycle([row.model_dump() for row in payload.rows], x_opex_user, payload.file_name)


@router.get("/audit-log")
def audit_log(
    request: Request,
    limit: int = 500,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewAuditLog")
    if _warehouse_scope(request, x_opex_role) is not None:
        raise HTTPException(status_code=403, detail="Depo kapsamlı rollere tenant geneli denetim kaydı açılamaz.")
    return {"rows": list_audit(limit)}


@router.get("/rules")
def rules() -> dict:
    return {"rows": list_rules()}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def add_rule_version(
    payload: RuleVersionCreateRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRules")
    _require_global_scope(request, x_opex_role, "Çalışma kuralı yönetimi")
    return create_rule_version(payload.model_dump(), x_opex_user)


@router.get("/devices")
def devices(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageDevices")
    return {"rows": _scoped_rows(request, x_opex_role, list_device_bindings())}


@router.post("/devices/{person_id}/reset")
def reset_device(
    person_id: str,
    payload: DeviceResetRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageDevices")
    _require_rows_in_scope(request, x_opex_role, [{"person_id": person_id}])
    return reset_device_binding(person_id, payload.model_dump(), x_opex_user)


@router.post("/devices/register", status_code=status.HTTP_201_CREATED)
def add_device(
    payload: DeviceRegisterRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return register_device(payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/devices/challenge", status_code=status.HTTP_201_CREATED)
def device_challenge(
    payload: DeviceChallengeRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return issue_device_challenge(payload.person_id, payload.device_id, x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/attendance")
def attendance(request: Request, person_id: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    scoped = _scoped_person_id(request, person_id, x_opex_role)
    rows = list_attendance()
    rows = rows if scoped is None else [item for item in rows if item.get("person_id") == scoped]
    return {"rows": _scoped_rows(request, x_opex_role, rows)}


@router.get("/daily-status")
def daily_status(request: Request, person_id: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    scoped = _scoped_person_id(request, person_id, x_opex_role)
    rows = list_daily_status()
    rows = rows if scoped is None else [item for item in rows if item.get("person_id") == scoped]
    return {"rows": _scoped_rows(request, x_opex_role, rows)}


@router.post("/attendance/import")
def attendance_import(
    payload: AttendanceImportRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_any(x_opex_role, x_opex_permissions, "manualCorrection", "importRoster")
    _require_rows_in_scope(request, x_opex_role, [row.model_dump() for row in payload.rows])
    return import_attendance([row.model_dump() for row in payload.rows], x_opex_user, payload.file_name)


@router.post("/leaves/import")
def leaves_import(
    payload: LeaveImportRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "importTimeOff")
    _require_rows_in_scope(request, x_opex_role, [row.model_dump() for row in payload.rows])
    return import_leaves([row.model_dump() for row in payload.rows], x_opex_user, payload.file_name)


@router.get("/shifts")
def shifts(request: Request, person_id: str | None = None, date: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    rows = list_shifts(_scoped_person_id(request, person_id, x_opex_role), date)
    return {"rows": _scoped_rows(request, x_opex_role, rows)}


@router.post("/shifts", status_code=status.HTTP_201_CREATED)
def add_shift(
    payload: ShiftCreateRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createShift")
    _require_rows_in_scope(request, x_opex_role, [payload.model_dump()])
    try:
        return create_shift(payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/shifts/{shift_id}/check-in", status_code=status.HTTP_201_CREATED)
def shift_check_in(
    shift_id: str,
    payload: CheckInRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return check_in(shift_id, payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/shifts/{shift_id}/check-out")
def shift_check_out(
    shift_id: str,
    payload: CheckOutRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return check_out(shift_id, payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/breaks")
def breaks(request: Request, person_id: str | None = None, shift_id: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    rows = list_breaks(_scoped_person_id(request, person_id, x_opex_role), shift_id)
    return {"rows": _scoped_rows(request, x_opex_role, rows)}


@router.post("/shifts/{shift_id}/breaks", status_code=status.HTTP_201_CREATED)
def break_action(
    shift_id: str,
    payload: BreakActionRequest,
    request: Request,
    x_opex_user: str = Header(default="picker", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return change_break(shift_id, payload.person_id, payload.action, x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/attendance/{attendance_id}/manual-correction")
def manual_correction(
    attendance_id: str,
    payload: ManualCorrectionRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manualCorrection")
    rows = [row for row in list_attendance() if row.get("id") == attendance_id]
    if rows:
        _require_rows_in_scope(request, x_opex_role, rows)
    result = correct_attendance(attendance_id, payload.model_dump(), x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Puantaj kaydı bulunamadı.")
    return result


@router.post("/attendance/{attendance_id}/approve")
def approve(
    attendance_id: str,
    payload: ApprovalRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveAttendance")
    rows = [row for row in list_attendance() if row.get("id") == attendance_id]
    if rows:
        _require_rows_in_scope(request, x_opex_role, rows)
    result = approve_attendance(attendance_id, x_opex_user, payload.note)
    if result is None:
        raise HTTPException(status_code=404, detail="Puantaj kaydı bulunamadı.")
    return result


@router.post("/attendance/bulk-approve")
def bulk_approve(
    payload: BulkApprovalRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "bulkApprove")
    rows = [row for row in list_attendance() if row.get("id") in payload.attendance_ids]
    if len(rows) != len(set(payload.attendance_ids)):
        raise HTTPException(status_code=404, detail="Puantaj kayıtlarından biri bulunamadı.")
    _require_rows_in_scope(request, x_opex_role, rows)
    rows = bulk_approve_attendance(payload.attendance_ids, x_opex_user, payload.note)
    return {"approved": len(rows), "rows": rows}


@router.get("/manager-tasks")
def manager_tasks(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "resolveManagerTasks")
    return {"rows": _scoped_rows(request, x_opex_role, list_manager_tasks())}


@router.post("/correction-requests", status_code=status.HTTP_201_CREATED)
def add_correction_request(
    payload: PickerCorrectionCreateRequest,
    request: Request,
    x_opex_user: str = Header(default="picker", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return create_correction_request(payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/manager-tasks/{task_id}/resolve")
def resolve_task(
    task_id: str,
    payload: ManagerTaskResolveRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "resolveManagerTasks")
    rows = [row for row in list_manager_tasks() if row.get("id") == task_id]
    if rows:
        _require_rows_in_scope(request, x_opex_role, rows)
    result = resolve_manager_task(task_id, payload.model_dump(), x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Yönetici görevi bulunamadı.")
    return result


@router.get("/announcements")
def announcements(request: Request, person_id: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    scoped_person = _scoped_person_id(request, person_id, x_opex_role)
    return {"rows": _scoped_announcements(request, x_opex_role, list_announcements(), scoped_person)}


@router.post("/announcements", status_code=status.HTTP_201_CREATED)
def add_announcement(
    payload: AnnouncementCreateRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageAnnouncements")
    _require_announcement_target_scope(request, x_opex_role, payload)
    return create_announcement(payload.model_dump(), x_opex_user)


@router.post("/announcements/{announcement_id}/dismiss")
def dismiss_one_announcement(
    announcement_id: str,
    payload: AnnouncementReceiptRequest,
    request: Request,
    x_opex_user: str = Header(default="picker", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    visible = _scoped_announcements(request, x_opex_role, list_announcements(), payload.person_id)
    if not any(str(row.get("id")) == str(announcement_id) for row in visible):
        raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
    try:
        return dismiss_announcement(announcement_id, payload.person_id, x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/notification-policy")
def notification_policy() -> dict:
    return get_notification_policy()


@router.get("/notifications")
def notifications(request: Request, person_id: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    return {"rows": list_notifications(_scoped_person_id(request, person_id, x_opex_role))}


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str, person_id: str, request: Request, x_opex_user: str = Header(default="picker", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    _enforce_self(request, person_id, x_opex_role)
    result = mark_notification_read(notification_id, person_id, x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı.")
    return result


@router.delete("/notifications/{notification_id}")
def remove_notification(notification_id: str, person_id: str, request: Request, x_opex_user: str = Header(default="picker", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    _enforce_self(request, person_id, x_opex_role)
    if not delete_notification(notification_id, person_id, x_opex_user):
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı.")
    return {"deleted": True}


@router.delete("/notifications")
def remove_all_notifications(person_id: str, request: Request, x_opex_user: str = Header(default="picker", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    _enforce_self(request, person_id, x_opex_role)
    return {"deleted": clear_notifications(person_id, x_opex_user)}


@router.get("/leave-requests")
def leave_requests(request: Request, person_id: str | None = None, warehouse: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    rows = list_leave_requests(_scoped_person_id(request, person_id, x_opex_role), warehouse)
    return {"rows": _scoped_rows(request, x_opex_role, rows)}


@router.post("/leave-requests", status_code=status.HTTP_201_CREATED)
def add_leave_request(payload: LeaveRequestCreateRequest, request: Request, x_opex_user: str = Header(default="picker", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return create_leave_request(payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/leave-requests/{request_id}/resolve")
def resolve_leave(request_id: str, payload: LeaveRequestResolveRequest, request: Request, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "resolveManagerTasks")
    rows = [row for row in list_leave_requests() if row.get("id") == request_id]
    if rows:
        _require_rows_in_scope(request, x_opex_role, rows)
    result = resolve_leave_request(request_id, payload.model_dump(), x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="İzin talebi bulunamadı.")
    return result


@router.get("/feature-flags")
def feature_flags() -> dict:
    return get_feature_flags()


@router.put("/feature-flags")
def put_feature_flags(
    payload: FeatureFlagsUpdateRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageSystemConfig")
    _require_global_scope(request, x_opex_role, "Feature flag yönetimi")
    return update_feature_flags(payload.model_dump(), x_opex_user)


@router.put("/notification-policy")
def put_notification_policy(
    payload: NotificationPolicyUpdateRequest,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageNotifications")
    _require_global_scope(request, x_opex_role, "Bildirim politikası yönetimi")
    return update_notification_policy(payload.model_dump(), x_opex_user)
