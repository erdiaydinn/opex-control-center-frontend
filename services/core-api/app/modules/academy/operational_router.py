from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.operational_schemas import (
    OperationalMappingCreateRequest,
    OperationalMappingRetireRequest,
    OperationalOutcomeObservationRequest,
    OperationalSignalIngestRequest,
)
from app.modules.academy.operational_service import (
    create_mapping,
    ingest_signal,
    mappings,
    my_readiness,
    record_outcome,
    retire_mapping,
)
from app.modules.academy.service import require_module

router = APIRouter(prefix="/operational-readiness", tags=["academy-operational-readiness"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
ReadinessUser = Annotated[
    Principal,
    Depends(require_permission("feature:academy:operationalReadiness")),
]
ReadinessAdmin = Annotated[
    Principal,
    Depends(require_permission("action:academy:manageOperationalReadiness")),
]
SignalWriter = Annotated[
    Principal,
    Depends(require_permission("action:academy:ingestOperationalSignals")),
]
OutcomeWriter = Annotated[
    Principal,
    Depends(require_permission("action:academy:recordOperationalOutcomes")),
]


def _bad_request(exc: ValueError) -> HTTPException:
    detail = str(exc)
    code = status.HTTP_409_CONFLICT if "already" in detail else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=detail)


@router.get("/me")
async def get_my_operational_readiness(
    session: TenantSession,
    principal: ReadinessUser,
) -> dict[str, object]:
    await require_module(session, principal)
    items = await my_readiness(session, principal)
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "items": items,
        "causal_attribution": False,
        "policy": "operational_gap_v1",
    }


@router.get("/admin/mappings")
async def get_operational_mappings(
    session: TenantSession,
    principal: ReadinessAdmin,
) -> dict[str, object]:
    await require_module(session, principal)
    items = await mappings(session, principal)
    return {"items": items}


@router.post("/admin/mappings", status_code=status.HTTP_201_CREATED)
async def post_operational_mapping(
    payload: OperationalMappingCreateRequest,
    session: TenantSession,
    principal: ReadinessAdmin,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        return await create_mapping(session, principal, payload)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/admin/mappings/{mapping_id}/retire")
async def post_operational_mapping_retirement(
    mapping_id: UUID,
    payload: OperationalMappingRetireRequest,
    request: Request,
    session: TenantSession,
    principal: ReadinessAdmin,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        return await retire_mapping(
            session,
            principal,
            mapping_id=mapping_id,
            reason=payload.reason,
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/signals", status_code=status.HTTP_201_CREATED)
async def post_operational_signal(
    payload: OperationalSignalIngestRequest,
    request: Request,
    session: TenantSession,
    principal: SignalWriter,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        return await ingest_signal(
            session,
            principal,
            payload,
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/remediations/{remediation_id}/observations", status_code=status.HTTP_201_CREATED)
async def post_operational_outcome_observation(
    remediation_id: UUID,
    payload: OperationalOutcomeObservationRequest,
    request: Request,
    session: TenantSession,
    principal: OutcomeWriter,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        return await record_outcome(
            session,
            principal,
            remediation_id=remediation_id,
            payload=payload,
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
