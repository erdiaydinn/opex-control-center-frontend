from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def create_badge_definition(
    session: AsyncSession,
    principal: Principal,
    *,
    badge_key: str,
    version_number: int,
    skill_id: UUID,
    minimum_level: int,
    title_i18n: dict[str, str],
    description_i18n: dict[str, str],
    criteria_i18n: dict[str, str],
    validity_days: int | None,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_badge_definitions (
                        tenant_id, badge_key, version_number, skill_id,
                        minimum_level, title_i18n, description_i18n,
                        criteria_i18n, validity_days, created_by
                    )
                    SELECT
                        skill.tenant_id,
                        CAST(:badge_key AS varchar(160)),
                        :version_number,
                        skill.id,
                        :minimum_level,
                        CAST(:title_i18n AS jsonb),
                        CAST(:description_i18n AS jsonb),
                        CAST(:criteria_i18n AS jsonb),
                        :validity_days,
                        CAST(:actor AS varchar(255))
                    FROM academy_skills AS skill
                    WHERE skill.tenant_id = :tenant_id
                      AND skill.id = :skill_id
                      AND skill.status = 'active'
                    RETURNING id, badge_key, version_number, skill_id,
                              minimum_level, title_i18n, description_i18n,
                              criteria_i18n, validity_days, created_by, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "badge_key": badge_key,
                    "version_number": version_number,
                    "skill_id": skill_id,
                    "minimum_level": minimum_level,
                    "title_i18n": json.dumps(title_i18n, ensure_ascii=False),
                    "description_i18n": json.dumps(description_i18n, ensure_ascii=False),
                    "criteria_i18n": json.dumps(criteria_i18n, ensure_ascii=False),
                    "validity_days": validity_days,
                    "actor": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def retire_badge_definition(
    session: AsyncSession,
    principal: Principal,
    *,
    badge_definition_id: UUID,
    reason: str,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_badge_definition_retirements (
                        tenant_id, badge_definition_id, reason,
                        retired_by, request_id
                    )
                    SELECT
                        definition.tenant_id,
                        definition.id,
                        CAST(:reason AS text),
                        CAST(:actor AS varchar(255)),
                        CAST(:request_id AS varchar(128))
                    FROM academy_badge_definitions AS definition
                    WHERE definition.tenant_id = :tenant_id
                      AND definition.id = :badge_definition_id
                    RETURNING id, badge_definition_id, reason,
                              retired_by, request_id, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "badge_definition_id": badge_definition_id,
                    "reason": reason,
                    "actor": principal.subject,
                    "request_id": request_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def issue_badge_award(
    session: AsyncSession,
    principal: Principal,
    *,
    badge_definition_id: UUID,
    skill_evidence_id: UUID,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_badge_awards (
                        tenant_id, badge_definition_id, skill_evidence_id,
                        subject, skill_id, observed_level,
                        evidence_type, evidence_ref,
                        issuer_subject, request_id
                    )
                    SELECT
                        evidence.tenant_id,
                        :badge_definition_id,
                        evidence.id,
                        evidence.subject,
                        evidence.skill_id,
                        evidence.observed_level,
                        evidence.evidence_type,
                        evidence.evidence_ref,
                        CAST(:actor AS varchar(255)),
                        CAST(:request_id AS varchar(128))
                    FROM academy_skill_evidence AS evidence
                    WHERE evidence.tenant_id = :tenant_id
                      AND evidence.id = :skill_evidence_id
                    RETURNING id, badge_definition_id, skill_evidence_id,
                              subject, skill_id, observed_level,
                              evidence_type, evidence_ref,
                              issuer_subject, issued_at, expires_at,
                              request_id, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "badge_definition_id": badge_definition_id,
                    "skill_evidence_id": skill_evidence_id,
                    "actor": principal.subject,
                    "request_id": request_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def revoke_badge_award(
    session: AsyncSession,
    principal: Principal,
    *,
    badge_award_id: UUID,
    reason: str,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_badge_revocations (
                        tenant_id, badge_award_id, reason,
                        revoked_by, request_id
                    )
                    SELECT
                        award.tenant_id,
                        award.id,
                        CAST(:reason AS text),
                        CAST(:actor AS varchar(255)),
                        CAST(:request_id AS varchar(128))
                    FROM academy_badge_awards AS award
                    WHERE award.tenant_id = :tenant_id
                      AND award.id = :badge_award_id
                    RETURNING id, badge_award_id, reason,
                              revoked_by, request_id, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "badge_award_id": badge_award_id,
                    "reason": reason,
                    "actor": principal.subject,
                    "request_id": request_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def list_my_badge_credentials(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT badge_award_id, badge_definition_id, badge_key,
                           badge_version, title_i18n, description_i18n,
                           criteria_i18n, subject, skill_id, observed_level,
                           skill_evidence_id, evidence_type, evidence_ref,
                           issuer_subject, issued_at, expires_at,
                           revoked_at, revoked_by, revocation_reason,
                           expired, revoked, valid,
                           credential_profile, signed_portable_credential
                    FROM academy_badge_credential_authority
                    WHERE tenant_id = :tenant_id
                      AND subject = CAST(:subject AS varchar(255))
                    ORDER BY issued_at DESC, badge_award_id DESC
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def get_my_badge_credential(
    session: AsyncSession,
    principal: Principal,
    *,
    badge_award_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT badge_award_id, badge_definition_id, badge_key,
                           badge_version, title_i18n, description_i18n,
                           criteria_i18n, subject, skill_id, observed_level,
                           skill_evidence_id, evidence_type, evidence_ref,
                           issuer_subject, issued_at, expires_at,
                           revoked_at, revoked_by, revocation_reason,
                           expired, revoked, valid,
                           credential_profile, signed_portable_credential
                    FROM academy_badge_credential_authority
                    WHERE tenant_id = :tenant_id
                      AND badge_award_id = :badge_award_id
                      AND subject = CAST(:subject AS varchar(255))
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "badge_award_id": badge_award_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None
