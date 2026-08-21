from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.authorization import require_permission, resolve_permission_scope
from app.core.security import Principal, get_current_principal
from app.field_evidence_object_routes import router as evidence_object_router
from app.field_governance_routes import router as governance_router
from app.modules.field_intelligence.authorization import require_field_permission
from app.modules.field_intelligence.planogram_compliance_promotion import (
    ADAPTER_KEY as PLANOGRAM_COMPLIANCE_ADAPTER,
)
from app.modules.field_intelligence.planogram_compliance_promotion import (
    create_planogram_compliance_promotion,
)
from app.modules.field_intelligence.promotion import (
    FieldPromotionError,
    create_promotion_request,
    decide_promotion_request,
    get_adapter,
    list_promotion_requests,
    record_consumer_receipt,
)
from app.modules.field_intelligence.promotion_access import get_promotion_authorization_context
from app.modules.field_intelligence.repository import list_locations

router = APIRouter()
promotion_router = APIRouter(prefix="/v1/field/promotions", tags=["field-promotion"])
FieldViewer = Annotated[
    Principal,
    Depends(require_permission("module:field_intelligence:view")),
]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromotionCreate(StrictModel):
    evidence_id: UUID
    adapter_key: Literal[
        "planogram.fixture_measurement.v1",
        "planogram.compliance_observation.v1",
        "inventory.count_observation.v1",
        "budget.supporting_evidence.v1",
    ]


class PromotionDecision(StrictModel):
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=1000)


class ConsumerReceipt(StrictModel):
    consumer_module: Literal["inventory", "planogram", "budget"]
    decision: Literal["accept", "reject"]
    destination_candidate_ref: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=1000)


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _field_allowed_location_ids(
    principal: Principal,
    permission_key: str,
) -> frozenset[str]:
    scope = require_field_permission(principal, permission_key)
    locations = await list_locations(str(principal.tenant_id), scope)
    return frozenset(str(item["location_id"]) for item in locations)


def _consumer_scope_allows(
    principal: Principal,
    *,
    consumer_module: str,
    location_id: str,
    candidate: dict[str, object],
) -> None:
    if consumer_module == "planogram":
        permission_key = "action:planogram:acceptFieldEvidence"
    else:
        adapter = next(
            item
            for item in (
                get_adapter("inventory.count_observation.v1"),
                get_adapter("budget.supporting_evidence.v1"),
            )
            if item.consumer_module == consumer_module
        )
        permission_key = adapter.consumer_permission
    scope = resolve_permission_scope(principal, permission_key)
    if scope.unrestricted:
        return
    if consumer_module == "budget":
        cost_center = str(candidate.get("cost_center") or "")
        if cost_center and cost_center in scope.values("cost_centers"):
            return
    else:
        allowed_locations = scope.values("warehouses") | scope.values("locations")
        if location_id in allowed_locations:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Consumer permission scope does not cover this Field promotion",
    )


@promotion_router.get("")
async def get_field_promotions(
    principal: FieldViewer,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    allowed = await _field_allowed_location_ids(
        principal,
        "action:field_intelligence:viewPromotions",
    )
    items = await list_promotion_requests(
        tenant_id=str(principal.tenant_id),
        allowed_location_ids=allowed,
        limit=limit,
    )
    return {
        "count": len(items),
        "items": items,
        "truth_boundary": {
            "field_evidence_is_consumer_truth": False,
            "consumer_truth_mutation_permitted": False,
            "separate_consumer_workflow_required": True,
        },
    }


@promotion_router.post("", status_code=status.HTTP_201_CREATED)
async def post_field_promotion(
    payload: PromotionCreate,
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _field_allowed_location_ids(
        principal,
        "action:field_intelligence:proposePromotion",
    )
    try:
        if payload.adapter_key == PLANOGRAM_COMPLIANCE_ADAPTER:
            return await create_planogram_compliance_promotion(
                tenant_id=str(principal.tenant_id),
                actor_subject=principal.subject,
                evidence_id=str(payload.evidence_id),
                allowed_location_ids=allowed,
            )
        return await create_promotion_request(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            evidence_id=str(payload.evidence_id),
            adapter_key=payload.adapter_key,
            allowed_location_ids=allowed,
        )
    except FieldPromotionError as exc:
        raise _bad_request(exc) from exc


@promotion_router.post("/{promotion_id}/decision")
async def post_field_promotion_decision(
    promotion_id: UUID,
    payload: PromotionDecision,
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _field_allowed_location_ids(
        principal,
        "action:field_intelligence:approvePromotion",
    )
    try:
        return await decide_promotion_request(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            promotion_id=str(promotion_id),
            decision=payload.decision,
            reason=payload.reason,
            allowed_location_ids=allowed,
        )
    except FieldPromotionError as exc:
        raise _bad_request(exc) from exc


@promotion_router.post("/{promotion_id}/consumer-receipt")
async def post_field_promotion_consumer_receipt(
    promotion_id: UUID,
    payload: ConsumerReceipt,
    principal: CurrentPrincipal,
) -> dict[str, object]:
    try:
        context = await get_promotion_authorization_context(
            tenant_id=str(principal.tenant_id),
            promotion_id=str(promotion_id),
        )
        if str(context["consumer_module"]) != payload.consumer_module:
            raise FieldPromotionError("consumer module does not match governed promotion adapter")
        if str(context.get("field_decision") or "") != "approve":
            raise FieldPromotionError("consumer receipt requires explicit Field approval")
        if context.get("consumer_receipt_id") is not None:
            raise FieldPromotionError("promotion already has an immutable consumer receipt")
        _consumer_scope_allows(
            principal,
            consumer_module=payload.consumer_module,
            location_id=str(context["location_id"]),
            candidate=dict(context["candidate_payload"]),
        )
        return await record_consumer_receipt(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            promotion_id=str(promotion_id),
            consumer_module=payload.consumer_module,
            decision=payload.decision,
            destination_candidate_ref=payload.destination_candidate_ref,
            reason=payload.reason,
        )
    except FieldPromotionError as exc:
        raise _bad_request(exc) from exc


router.include_router(promotion_router)
router.include_router(evidence_object_router)
router.include_router(governance_router)
