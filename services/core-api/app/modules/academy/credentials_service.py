from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.credentials_schemas import (
    BadgeAwardIssueRequest,
    BadgeDefinitionCreateRequest,
    BadgeRetirementRequest,
    BadgeRevocationRequest,
)
from app.modules.academy.repository import record_platform_audit
from app.modules.academy.repository_credentials import (
    create_badge_definition,
    get_my_badge_credential,
    issue_badge_award,
    list_my_badge_credentials,
    retire_badge_definition,
    revoke_badge_award,
)


async def create_definition(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    payload: BadgeDefinitionCreateRequest,
) -> dict[str, Any]:
    try:
        result = await create_badge_definition(
            session,
            principal,
            badge_key=payload.badge_key,
            version_number=payload.version_number,
            skill_id=payload.skill_id,
            minimum_level=payload.minimum_level,
            title_i18n=payload.title_i18n,
            description_i18n=payload.description_i18n,
            criteria_i18n=payload.criteria_i18n,
            validity_days=payload.validity_days,
        )
    except IntegrityError as exc:
        raise ValueError("badge definition version already exists") from exc

    if result is None:
        raise ValueError("badge definition requires an active Academy skill")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.credential.definition_created",
        resource_type="academy_badge_definition",
        resource_id=str(result["id"]),
        data={
            "badge_key": result["badge_key"],
            "version_number": result["version_number"],
            "skill_id": str(result["skill_id"]),
            "minimum_level": result["minimum_level"],
        },
    )
    return result


async def retire_definition(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    badge_definition_id: UUID,
    payload: BadgeRetirementRequest,
) -> dict[str, Any]:
    try:
        result = await retire_badge_definition(
            session,
            principal,
            badge_definition_id=badge_definition_id,
            reason=payload.reason,
            request_id=request_id,
        )
    except IntegrityError as exc:
        raise ValueError("badge definition is already retired") from exc

    if result is None:
        raise ValueError("badge definition not found")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.credential.definition_retired",
        resource_type="academy_badge_definition",
        resource_id=str(badge_definition_id),
        data={"reason_recorded": True},
    )
    return result


async def issue_award(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    payload: BadgeAwardIssueRequest,
) -> dict[str, Any]:
    try:
        result = await issue_badge_award(
            session,
            principal,
            badge_definition_id=payload.badge_definition_id,
            skill_evidence_id=payload.skill_evidence_id,
            request_id=request_id,
        )
    except IntegrityError as exc:
        raise ValueError("badge award already exists for this evidence") from exc
    except DBAPIError as exc:
        raise ValueError("skill evidence is not eligible for this badge definition") from exc

    if result is None:
        raise ValueError("skill evidence not found")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.credential.award_issued",
        resource_type="academy_badge_award",
        resource_id=str(result["id"]),
        data={
            "badge_definition_id": str(result["badge_definition_id"]),
            "skill_evidence_id": str(result["skill_evidence_id"]),
            "subject": result["subject"],
            "skill_id": str(result["skill_id"]),
            "observed_level": result["observed_level"],
        },
    )
    return result


async def revoke_award(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    badge_award_id: UUID,
    payload: BadgeRevocationRequest,
) -> dict[str, Any]:
    try:
        result = await revoke_badge_award(
            session,
            principal,
            badge_award_id=badge_award_id,
            reason=payload.reason,
            request_id=request_id,
        )
    except IntegrityError as exc:
        raise ValueError("badge award is already revoked") from exc

    if result is None:
        raise ValueError("badge award not found")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.credential.award_revoked",
        resource_type="academy_badge_award",
        resource_id=str(badge_award_id),
        data={"reason_recorded": True},
    )
    return result


async def my_credentials(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    return await list_my_badge_credentials(session, principal)


async def my_credential(
    session: AsyncSession,
    principal: Principal,
    *,
    badge_award_id: UUID,
) -> dict[str, Any] | None:
    return await get_my_badge_credential(
        session,
        principal,
        badge_award_id=badge_award_id,
    )
