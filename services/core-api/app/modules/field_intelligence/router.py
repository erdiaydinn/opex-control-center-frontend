from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import Principal, get_current_principal

from .authorization import require_field_permission
from .repository import (
    FieldRepositoryError,
    create_mission,
    create_template,
    field_analytics,
    get_mission_detail,
    list_evidence,
    list_locations,
    list_missions,
    list_templates,
    queue_notification_intents,
    review_evidence,
    set_mission_status,
    submit_evidence,
    upsert_location,
)
from .schemas import (
    EvidenceReview,
    EvidenceSubmit,
    LocationUpsert,
    MissionCreate,
    NotificationIntentCreate,
    TemplateCreate,
)

router = APIRouter(prefix="/v1/field", tags=["field-intelligence"])


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field resource not found in authorized scope")


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


@router.get("/missions/{mission_id}")
async def field_mission_detail(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "module:field_intelligence:view")
    item = await get_mission_detail(str(principal.tenant_id), scope, mission_id)
    if item is None:
        raise _not_found()
    return item


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


@router.post("/missions/{mission_id}/activate")
async def activate_field_mission(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:activateMission")
    try:
        return await set_mission_status(
            str(principal.tenant_id), scope, mission_id, transition="activate"
        )
    except FieldRepositoryError as exc:
        raise _bad_request(exc) from exc


@router.post("/missions/{mission_id}/cancel")
async def cancel_field_mission(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:cancelMission")
    try:
        return await set_mission_status(
            str(principal.tenant_id), scope, mission_id, transition="cancel"
        )
    except FieldRepositoryError as exc:
        raise _bad_request(exc) from exc


@router.post("/missions/{mission_id}/targets/{location_id}/evidence", status_code=status.HTTP_201_CREATED)
async def post_field_evidence(
    mission_id: str,
    location_id: str,
    payload: EvidenceSubmit,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:submitEvidence")
    try:
        return await submit_evidence(
            str(principal.tenant_id),
            principal.subject,
            scope,
            mission_id,
            location_id,
            payload,
        )
    except FieldRepositoryError as exc:
        raise _bad_request(exc) from exc


@router.get("/evidence")
async def field_evidence(
    mission_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:viewEvidence")
    items = await list_evidence(
        str(principal.tenant_id), scope, mission_id=mission_id, limit=limit
    )
    return {"count": len(items), "items": items}


@router.post("/evidence/{evidence_id}/review")
async def post_field_evidence_review(
    evidence_id: str,
    payload: EvidenceReview,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:reviewEvidence")
    try:
        return await review_evidence(
            str(principal.tenant_id), principal.subject, scope, evidence_id, payload
        )
    except FieldRepositoryError as exc:
        raise _bad_request(exc) from exc


@router.post("/missions/{mission_id}/notification-intents", status_code=status.HTTP_202_ACCEPTED)
async def post_field_notification_intents(
    mission_id: str,
    payload: NotificationIntentCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "action:field_intelligence:sendReminder")
    try:
        return await queue_notification_intents(
            str(principal.tenant_id), principal.subject, scope, mission_id, payload
        )
    except FieldRepositoryError as exc:
        raise _bad_request(exc) from exc


@router.get("/analytics")
async def get_field_analytics(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    scope = require_field_permission(principal, "feature:field_intelligence:analytics")
    return await field_analytics(str(principal.tenant_id), scope)


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
