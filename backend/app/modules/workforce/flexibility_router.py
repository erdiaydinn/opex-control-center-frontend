from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, Request, status

from .flexibility import (
    claim_open_shift,
    create_open_shift,
    list_availability,
    list_open_shifts_for_person,
    upsert_availability,
)
from .flexibility_schemas import (
    AvailabilityUpsertRequest,
    OpenShiftClaimRequest,
    OpenShiftCreateRequest,
    WorkActivityApproveRequest,
)
from .router import _enforce_self, _require, _require_rows_in_scope
from .work_activity_catalog import (
    approve_activity,
    list_activity_catalog,
    list_template_candidates,
    retire_activity,
)


router = APIRouter(prefix="/workforce/flexibility", tags=["Workforce Flexibility"])


def _actor(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    return str(getattr(identity, "subject", None) or request.headers.get("X-OPEX-User") or "unknown")


def _strict_employee_self(request: Request, person_id: str, role: str) -> None:
    """Employee marketplace actions never become manager impersonation paths.

    If a verified identity is present, its employee_id must match regardless of
    role. Production fails closed when the signed claim is absent. Legacy local
    development keeps the existing Workforce self-check behavior for fixtures.
    """
    identity = getattr(request.state, "identity", None)
    expected = getattr(identity, "employee_id", None)
    if expected:
        if str(expected) != str(person_id):
            raise HTTPException(status_code=403, detail="Başka personel adına esneklik veya açık vardiya işlemi yapılamaz.")
        _enforce_self(request, person_id, role)
        return
    if os.getenv("DOCKOS_ENV", "development").lower() == "production":
        raise HTTPException(status_code=403, detail="JWT employee_id claim'i gerekli.")
    _enforce_self(request, person_id, role)


@router.get("/availability")
def get_availability(
    person_id: str,
    request: Request,
    start_date: str | None = None,
    end_date: str | None = None,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _strict_employee_self(request, person_id, x_opex_role)
    return {"rows": list_availability(person_id, start_date, end_date)}


@router.put("/availability")
def put_availability(
    payload: AvailabilityUpsertRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _strict_employee_self(request, payload.person_id, x_opex_role)
    return upsert_availability(payload.model_dump(mode="json"), _actor(request))


@router.get("/open-shifts")
def get_open_shifts(
    person_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _strict_employee_self(request, person_id, x_opex_role)
    return {"rows": list_open_shifts_for_person(person_id)}


@router.get("/activities")
def get_activity_catalog(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createShift")
    return {"rows": list_activity_catalog()}


@router.get("/activity-templates/{template_key}")
def get_activity_template(
    template_key: str,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageSystemConfig")
    try:
        return {"template_key": template_key, "rows": list_template_candidates(template_key)}
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/activities", status_code=status.HTTP_201_CREATED)
def post_activity(
    payload: WorkActivityApproveRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageSystemConfig")
    return approve_activity(payload.model_dump(mode="json"), _actor(request))


@router.post("/activities/{activity_key}/retire")
def post_retire_activity(
    activity_key: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageSystemConfig")
    return retire_activity(activity_key, _actor(request))


@router.post("/open-shifts", status_code=status.HTTP_201_CREATED)
def post_open_shift(
    payload: OpenShiftCreateRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createShift")
    _require_rows_in_scope(request, x_opex_role, [{"warehouse_id": payload.warehouse_id}])
    return create_open_shift(payload.model_dump(mode="json"), _actor(request))


@router.post("/open-shifts/{open_shift_id}/claim")
def post_open_shift_claim(
    open_shift_id: str,
    payload: OpenShiftClaimRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _strict_employee_self(request, payload.person_id, x_opex_role)
    return claim_open_shift(open_shift_id, payload.person_id, _actor(request))
