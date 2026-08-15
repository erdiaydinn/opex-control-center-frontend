from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import Principal, get_current_principal

from .authorization import require_field_permission
from .repository import (
    FieldRepositoryError,
    create_mission,
    create_template,
    list_locations,
    list_missions,
    list_templates,
    upsert_location,
)
from .schemas import LocationUpsert, MissionCreate, TemplateCreate

router = APIRouter(prefix="/v1/field", tags=["field-intelligence"])


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/bootstrap")
async def field_bootstrap(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    tenant_id = str(principal.tenant_id)
    locations = await list_locations(tenant_id, scope)
    templates = await list_templates(tenant_id)
    missions = await list_missions(tenant_id, scope)
    return {
        "tenant_id": tenant_id,
        "scope": scope.model_dump(mode="json"),
        "locations": locations,
        "templates": templates,
        "missions": missions,
    }


@router.get("/missions")
async def field_missions(
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    items = await list_missions(str(principal.tenant_id), scope, limit=limit)
    return {"count": len(items), "items": items}


@router.post("/missions", status_code=status.HTTP_201_CREATED)
async def create_field_mission(
    payload: MissionCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:createMission")
    if payload.activate:
        require_field_permission(principal, "action:field_intelligence:activateMission")
    try:
        return await create_mission(
            str(principal.tenant_id),
            principal.subject,
            payload,
            scope,
        )
    except FieldRepositoryError as exc:
        raise _bad_request(exc) from exc


@router.get("/locations")
async def field_locations(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    items = await list_locations(str(principal.tenant_id), scope)
    return {"count": len(items), "items": items}


@router.put("/locations/{location_id}")
async def put_field_location(
    location_id: str,
    payload: LocationUpsert,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:manageLocations")
    if location_id != payload.location_id:
        raise HTTPException(status_code=400, detail="location path/body identity mismatch")
    if not scope.unrestricted:
        allowed = location_id in scope.location_ids or (
            payload.region is not None and payload.region in scope.regions
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="location is outside Field Intelligence scope")
    return await upsert_location(str(principal.tenant_id), payload)


@router.get("/templates")
async def field_templates(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    require_field_permission(principal, "module:field_intelligence:view")
    items = await list_templates(str(principal.tenant_id))
    return {"count": len(items), "items": items}


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def post_field_template(
    payload: TemplateCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    require_field_permission(principal, "action:field_intelligence:manageTemplates")
    try:
        return await create_template(str(principal.tenant_id), principal.subject, payload)
    except ValueError as exc:
        raise _bad_request(exc) from exc
