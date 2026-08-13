import os

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


def _enforce_self(request: Request, person_id: str, role: str) -> None:
    if role.strip().lower().replace("-", "_").replace(" ", "_") in {"admin", "administrator", "super_admin", "superadmin", "manager", "warehouse_manager", "hr"}:
        return
    identity = getattr(request.state, "identity", None)
    expected = getattr(identity, "employee_id", None)
    if expected and str(expected) == str(person_id):
        return
    # Development legacy mode keeps existing test/demo access working. In
    # production every picker JWT must contain the employee_id claim.
    import os
    if os.getenv("DOCKOS_ENV", "development").lower() != "production":
        return
    raise HTTPException(status_code=403, detail="Yalnızca kendi Workforce kaydınıza erişebilirsiniz.")


def _scoped_person_id(request: Request, requested: str | None, role: str) -> str | None:
    if role.strip().lower().replace("-", "_").replace(" ", "_") in {"admin", "administrator", "super_admin", "superadmin", "manager", "warehouse_manager", "hr"}:
        return requested
    identity = getattr(request.state, "identity", None)
    expected = getattr(identity, "employee_id", None)
    if expected:
        if requested and str(requested) != str(expected):
            raise HTTPException(status_code=403, detail="Başka personele ait kayıt görüntülenemez.")
        return str(expected)
    import os
    if os.getenv("DOCKOS_ENV", "development").lower() == "production":
        raise HTTPException(status_code=403, detail="JWT employee_id claim'i gerekli.")
    return requested


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
        "pii_encryption_key": bool(os.getenv("OPEX_PII_KEY")),
        "apple_app_attest": bool(os.getenv("APPLE_APP_ATTEST_VERIFY_URL")),
        "google_play_integrity": bool(os.getenv("GOOGLE_PLAY_INTEGRITY_VERIFY_URL")),
        "local_user_presence_required": production or os.getenv("WORKFORCE_REQUIRE_LOCAL_AUTH", "false").lower() == "true",
        "continuous_location_tracking": False,
        "biometric_template_storage": False,
    }
    required = (
        "postgresql", "tenant_id", "atomic_snapshot_audit", "oidc", "pii_encryption_key",
        "apple_app_attest", "google_play_integrity", "local_user_presence_required",
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
def warehouses() -> dict:
    return {"rows": list_warehouses()}


@router.post("/warehouses")
def save_warehouse(payload: WarehouseUpsertRequest, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageWarehouses")
    return upsert_warehouse(payload.model_dump(), x_opex_user)


@router.patch("/warehouses")
def patch_warehouses(payload: WarehouseBulkPatchRequest, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageWarehouses")
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
        "announcements": list_announcements(),
        "announcement_receipts": list_announcement_receipts(person_id),
        "features": get_feature_flags(),
        "notification_policy": get_notification_policy(),
    }


@router.get("/admin/bootstrap")
def admin_bootstrap(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewWorkforce")
    sensitive = is_action_allowed(x_opex_role, x_opex_permissions, "viewSensitiveIdentity") or is_action_allowed(x_opex_role, x_opex_permissions, "viewFullNationalId")
    return {
        "people": list_people(sensitive),
        "warehouses": list_warehouses(),
        "rules": list_rules(),
        "shifts": list_shifts(),
        "attendance": list_attendance(),
        "leaves": list_leaves(),
        "devices": list_device_bindings(),
        "leave_requests": list_leave_requests(),
        "manager_tasks": list_manager_tasks(),
        "announcements": list_announcements(),
        "features": get_feature_flags(),
        "notification_policy": get_notification_policy(),
        "audit": list_audit(1000) if is_action_allowed(x_opex_role, x_opex_permissions, "viewAuditLog") else [],
    }


@router.get("/people")
def people(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewPeople")
    sensitive = is_action_allowed(x_opex_role, x_opex_permissions, "viewSensitiveIdentity") or is_action_allowed(x_opex_role, x_opex_permissions, "viewFullNationalId")
    return {"rows": list_people(sensitive)}


@router.post("/people/bulk-upsert")
def people_bulk_upsert(
    payload: PeopleBulkUpsertRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_any(x_opex_role, x_opex_permissions, "managePeople", "manageEmployees")
    return upsert_people([row.model_dump() for row in payload.rows], x_opex_user)


@router.post("/people/employment-lifecycle/import")
def employment_lifecycle_import(
    payload: EmploymentLifecycleImportRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_any(x_opex_role, x_opex_permissions, "managePeople", "manageEmployees")
    return update_employment_lifecycle([row.model_dump() for row in payload.rows], x_opex_user, payload.file_name)


@router.get("/audit-log")
def audit_log(
    limit: int = 500,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewAuditLog")
    return {"rows": list_audit(limit)}


@router.get("/rules")
def rules() -> dict:
    return {"rows": list_rules()}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def add_rule_version(
    payload: RuleVersionCreateRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRules")
    return create_rule_version(payload.model_dump(), x_opex_user)


@router.get("/devices")
def devices(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageDevices")
    return {"rows": list_device_bindings()}


@router.post("/devices/{person_id}/reset")
def reset_device(
    person_id: str,
    payload: DeviceResetRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageDevices")
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
    return {"rows": rows if scoped is None else [item for item in rows if item.get("person_id") == scoped]}


@router.post("/attendance/import")
def attendance_import(
    payload: AttendanceImportRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_any(x_opex_role, x_opex_permissions, "manualCorrection", "importRoster")
    return import_attendance([row.model_dump() for row in payload.rows], x_opex_user, payload.file_name)


@router.post("/leaves/import")
def leaves_import(
    payload: LeaveImportRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "importTimeOff")
    return import_leaves([row.model_dump() for row in payload.rows], x_opex_user, payload.file_name)


@router.get("/shifts")
def shifts(request: Request, person_id: str | None = None, date: str | None = None, x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    return {"rows": list_shifts(_scoped_person_id(request, person_id, x_opex_role), date)}


@router.post("/shifts", status_code=status.HTTP_201_CREATED)
def add_shift(
    payload: ShiftCreateRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createShift")
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
    return {"rows": list_breaks(_scoped_person_id(request, person_id, x_opex_role), shift_id)}


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
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manualCorrection")
    result = correct_attendance(attendance_id, payload.model_dump(), x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Puantaj kaydı bulunamadı.")
    return result


@router.post("/attendance/{attendance_id}/approve")
def approve(
    attendance_id: str,
    payload: ApprovalRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveAttendance")
    result = approve_attendance(attendance_id, x_opex_user, payload.note)
    if result is None:
        raise HTTPException(status_code=404, detail="Puantaj kaydı bulunamadı.")
    return result


@router.post("/attendance/bulk-approve")
def bulk_approve(
    payload: BulkApprovalRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "bulkApprove")
    rows = bulk_approve_attendance(payload.attendance_ids, x_opex_user, payload.note)
    return {"approved": len(rows), "rows": rows}


@router.get("/manager-tasks")
def manager_tasks(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "resolveManagerTasks")
    return {"rows": list_manager_tasks()}


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
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "resolveManagerTasks")
    result = resolve_manager_task(task_id, payload.model_dump(), x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Yönetici görevi bulunamadı.")
    return result


@router.get("/announcements")
def announcements() -> dict:
    return {"rows": list_announcements()}


@router.post("/announcements", status_code=status.HTTP_201_CREATED)
def add_announcement(
    payload: AnnouncementCreateRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageAnnouncements")
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
    return {"rows": list_leave_requests(_scoped_person_id(request, person_id, x_opex_role), warehouse)}


@router.post("/leave-requests", status_code=status.HTTP_201_CREATED)
def add_leave_request(payload: LeaveRequestCreateRequest, request: Request, x_opex_user: str = Header(default="picker", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role")) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    try:
        return create_leave_request(payload.model_dump(), x_opex_user)
    except WorkforceRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/leave-requests/{request_id}/resolve")
def resolve_leave(request_id: str, payload: LeaveRequestResolveRequest, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "resolveManagerTasks")
    result = resolve_leave_request(request_id, payload.model_dump(), x_opex_user)
    if result is None:
        raise HTTPException(status_code=404, detail="İzin talebi bulunamadı.")
    return result


@router.get("/feature-flags")
def feature_flags() -> dict:
    return get_feature_flags()


@router.put("/feature-flags")
def put_feature_flags(payload: FeatureFlagsUpdateRequest, x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"), x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"), x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions")) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageSystemConfig")
    return update_feature_flags(payload.model_dump(), x_opex_user)


@router.put("/notification-policy")
def put_notification_policy(
    payload: NotificationPolicyUpdateRequest,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageNotifications")
    return update_notification_policy(payload.model_dump(), x_opex_user)
