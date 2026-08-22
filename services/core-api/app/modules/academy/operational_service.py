from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.operational_schemas import (
    OperationalMappingCreateRequest,
    OperationalOutcomeObservationRequest,
    OperationalSignalIngestRequest,
)
from app.modules.academy.repository_operational import (
    create_operational_mapping,
    ingest_operational_signal,
    list_my_operational_readiness,
    list_operational_mappings,
    record_operational_outcome,
    retire_operational_mapping,
)


async def create_mapping(
    session: AsyncSession,
    principal: Principal,
    payload: OperationalMappingCreateRequest,
) -> dict[str, object]:
    try:
        row = await create_operational_mapping(
            session,
            principal,
            **payload.model_dump(),
        )
    except IntegrityError as exc:
        raise ValueError("Operational readiness mapping already exists") from exc
    if row is None:
        raise ValueError("Operational mapping requires active skill and published learning path")
    return row


async def retire_mapping(
    session: AsyncSession,
    principal: Principal,
    *,
    mapping_id: UUID,
    reason: str,
    request_id: str,
) -> dict[str, object]:
    try:
        row = await retire_operational_mapping(
            session,
            principal,
            mapping_id=mapping_id,
            reason=reason,
            request_id=request_id,
        )
    except IntegrityError as exc:
        raise ValueError("Operational readiness mapping is already retired") from exc
    if row is None:
        raise ValueError("Operational readiness mapping not found or already retired")
    return row


async def mappings(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, object]]:
    return await list_operational_mappings(session, principal)


async def ingest_signal(
    session: AsyncSession,
    principal: Principal,
    payload: OperationalSignalIngestRequest,
    *,
    request_id: str,
) -> dict[str, object]:
    try:
        result = await ingest_operational_signal(
            session,
            principal,
            **payload.model_dump(),
            request_id=request_id,
        )
    except IntegrityError as exc:
        raise ValueError("Operational signal source event was already ingested") from exc
    if result is None:
        raise ValueError("Operational signal subject is not an active tenant member")
    return result


async def record_outcome(
    session: AsyncSession,
    principal: Principal,
    *,
    remediation_id: UUID,
    payload: OperationalOutcomeObservationRequest,
    request_id: str,
) -> dict[str, object]:
    try:
        row = await record_operational_outcome(
            session,
            principal,
            remediation_id=remediation_id,
            **payload.model_dump(),
            request_id=request_id,
        )
    except IntegrityError as exc:
        raise ValueError("Operational outcome observation already exists") from exc
    if row is None:
        raise ValueError("Operational outcome source is not authoritative for this remediation")
    return row


async def my_readiness(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, object]]:
    return await list_my_operational_readiness(session, principal)
