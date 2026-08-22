from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_job_repository import AgentJobRecord, PostgresAgentJobRepository
from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session

router = APIRouter(prefix="/v1/ai/agent-jobs", tags=["jarvis-agents"])
JarvisPrincipal = Annotated[Principal, Depends(require_permission("module:jarvis:view"))]


class CreateAgentJobRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=4000)
    requested_agent_count: int = Field(default=3, ge=1, le=16)


class AgentJobResponse(BaseModel):
    job_id: UUID
    objective_ref: str
    status: str
    version: int
    cancellation_epoch: int
    required_child_count: int
    completed_child_count: int
    effect_state: str


def _response(item: AgentJobRecord) -> AgentJobResponse:
    return AgentJobResponse(
        job_id=item.id,
        objective_ref=item.objective_ref,
        status=item.status,
        version=item.version,
        cancellation_epoch=item.cancellation_epoch,
        required_child_count=item.required_child_count,
        completed_child_count=item.completed_child_count,
        effect_state=item.effect_state,
    )


async def get_agent_job_repository(
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
) -> PostgresAgentJobRepository:
    return PostgresAgentJobRepository(session)


AgentRepository = Annotated[PostgresAgentJobRepository, Depends(get_agent_job_repository)]


@router.post("", response_model=AgentJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_agent_job(
    payload: CreateAgentJobRequest,
    principal: JarvisPrincipal,
    repository: AgentRepository,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=240)],
) -> AgentJobResponse:
    item, _ = await repository.create(
        tenant_id=principal.tenant_id,
        requested_by=principal.subject,
        idempotency_key=idempotency_key,
        objective_ref=payload.objective,
        required_child_count=payload.requested_agent_count,
    )
    return _response(item)


@router.get("/{job_id}", response_model=AgentJobResponse)
async def get_agent_job(
    job_id: UUID,
    principal: JarvisPrincipal,
    repository: AgentRepository,
) -> AgentJobResponse:
    item = await repository.get(tenant_id=principal.tenant_id, job_id=job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    return _response(item)


@router.get("/{job_id}/events")
async def list_agent_job_events(
    job_id: UUID,
    principal: JarvisPrincipal,
    repository: AgentRepository,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, object]:
    item = await repository.get(tenant_id=principal.tenant_id, job_id=job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    events = await repository.events(
        tenant_id=principal.tenant_id,
        job_id=job_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return {"job_id": job_id, "events": events}


@router.post("/{job_id}/cancel", response_model=AgentJobResponse, status_code=202)
async def cancel_agent_job(
    job_id: UUID,
    principal: JarvisPrincipal,
    repository: AgentRepository,
) -> AgentJobResponse:
    item = await repository.cancel(
        tenant_id=principal.tenant_id,
        job_id=job_id,
        requested_by=principal.subject,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    return _response(item)
