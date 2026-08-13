from fastapi import APIRouter, Header, HTTPException, Request

from .schemas import (AdminPasswordResetRequest, LoginRequest, PasswordChangeRequest,
                      RefreshRequest, UserCreate, UserUpdate, WarehouseCreate)
from .service import (IdentityRuleError, change_password, create_user, create_warehouse,
                      list_users, list_warehouses, login, refresh,
                      reset_password_by_admin, update_user)

router = APIRouter(prefix="/identity", tags=["Identity V23"])


def _actor(request: Request) -> str:
    return getattr(getattr(request.state, "identity", None), "subject", "unknown")


def _admin(role: str) -> None:
    if role.lower().replace("-", "_") not in {"super_admin", "admin", "administrator"}:
        raise HTTPException(status_code=403, detail="Kullanıcı ve depo yönetimi için admin yetkisi gerekir.")


def _run(action, *args):
    try:
        return action(*args)
    except IdentityRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/login")
def local_login(payload: LoginRequest):
    return _run(login, payload.username, payload.password, payload.device_id)


@router.post("/refresh")
def local_refresh(payload: RefreshRequest):
    return _run(refresh, payload.refresh_token, payload.device_id)


@router.get("/admin/users")
def users(request: Request, role: str = Header("viewer", alias="X-OPEX-Role")):
    _admin(role)
    return {"rows": list_users()}


@router.post("/admin/users", status_code=201)
def add_user(payload: UserCreate, request: Request, role: str = Header("viewer", alias="X-OPEX-Role")):
    _admin(role)
    return _run(create_user, payload.model_dump(), _actor(request))


@router.patch("/admin/users/{user_id}")
def change_user(user_id: str, payload: UserUpdate, request: Request, role: str = Header("viewer", alias="X-OPEX-Role")):
    _admin(role)
    return _run(update_user, user_id, payload.model_dump(), _actor(request))


@router.post("/admin/users/password-reset")
def admin_password_reset(
    payload: AdminPasswordResetRequest,
    request: Request,
    role: str = Header("viewer", alias="X-OPEX-Role"),
):
    _admin(role)
    return _run(reset_password_by_admin, payload.username, _actor(request))


@router.post("/password/change")
def own_password_change(payload: PasswordChangeRequest, request: Request):
    identity = getattr(request.state, "identity", None)
    if not identity:
        raise HTTPException(status_code=401, detail="Geçerli oturum gerekli.")
    return _run(
        change_password,
        identity.subject,
        payload.current_password,
        payload.new_password,
        payload.device_id,
    )


@router.get("/admin/warehouses")
def warehouses(request: Request, role: str = Header("viewer", alias="X-OPEX-Role")):
    _admin(role)
    return {"rows": list_warehouses()}


@router.post("/admin/warehouses", status_code=201)
def add_warehouse(payload: WarehouseCreate, request: Request, role: str = Header("viewer", alias="X-OPEX-Role")):
    _admin(role)
    return _run(create_warehouse, payload.model_dump(), _actor(request))
