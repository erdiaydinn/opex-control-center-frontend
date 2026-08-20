from __future__ import annotations

from fastapi import APIRouter, Header, Request, status

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
)
from .router import _enforce_self, _require, _require_rows_in_scope


router = APIRouter(prefix="/workforce/flexibility", tags=["Workforce Flexibility"])


def _actor(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    return str(getattr(identity, "subject", None) or request.headers.get("X-OPEX-User") or "unknown")


@router.get("/availability")
def get_availability(
    person_id: str,
    request: Request,
    start_date: str | None = None,
    end_date: str | None = None,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, person_id, x_opex_role)
    return {"rows": list_availability(person_id, start_date, end_date)}


@router.put("/availability")
def put_availability(
    payload: AvailabilityUpsertRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, payload.person_id, x_opex_role)
    return upsert_availability(payload.model_dump(mode="json"), _actor(request))


@router.get("/open-shifts")
def get_open_shifts(
    person_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
) -> dict:
    _enforce_self(request, person_id, x_opex_role)
    return {"rows": list_open_shifts_for_person(person_id)}


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
    _enforce_self(request, payload.person_id, x_opex_role)
    return claim_open_shift(open_shift_id, payload.person_id, _actor(request))
