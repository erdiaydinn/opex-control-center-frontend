from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.localization import canonicalize_content_locale
from app.core.security import Principal
from app.modules.academy.localization_schemas import (
    LocaleSettingUpdateRequest,
    TranslationLineageCreateRequest,
    TranslationReviewRequest,
)
from app.modules.academy.repository import record_platform_audit
from app.modules.academy.repository_localization import (
    create_translation_lineage,
    list_locale_settings,
    list_translation_authority,
    review_translation,
    submit_translation,
    upsert_locale_setting,
)


async def localization_settings(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    return await list_locale_settings(session, principal)


async def configure_locale(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    locale: str,
    payload: LocaleSettingUpdateRequest,
) -> dict[str, Any]:
    canonical = canonicalize_content_locale(locale)
    if canonical is None:
        raise ValueError("unsupported Academy content locale")

    result = await upsert_locale_setting(
        session,
        principal,
        locale=canonical,
        enabled=payload.enabled,
        required=payload.required,
        is_default=payload.is_default,
        allow_machine_draft=payload.allow_machine_draft,
    )
    if result is None:
        raise ValueError("current default locale cannot be demoted or disabled directly")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.localization.configure_locale",
        resource_type="academy_locale_setting",
        resource_id=canonical,
        data={
            "enabled": result["enabled"],
            "required": result["required"],
            "is_default": result["is_default"],
            "allow_machine_draft": result["allow_machine_draft"],
        },
    )
    return result


async def author_translation_lineage(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    payload: TranslationLineageCreateRequest,
) -> dict[str, Any]:
    try:
        result = await create_translation_lineage(
            session,
            principal,
            source_version_id=payload.source_version_id,
            target_version_id=payload.target_version_id,
            translation_method=payload.translation_method,
        )
    except IntegrityError as exc:
        raise ValueError("target content version already has translation lineage") from exc

    if result is None:
        raise ValueError(
            "translation lineage requires same-content versions, a published source, "
            "an enabled target locale and an allowed translation method"
        )

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.localization.create_translation",
        resource_type="academy_translation_lineage",
        resource_id=str(result["id"]),
        data={
            "content_id": str(result["content_id"]),
            "source_version_id": str(result["source_version_id"]),
            "target_version_id": str(result["target_version_id"]),
            "source_locale": result["source_locale"],
            "target_locale": result["target_locale"],
            "translation_method": result["translation_method"],
        },
    )
    return result


async def submit_translation_for_review(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    translation_id: UUID,
) -> dict[str, Any]:
    try:
        result = await submit_translation(
            session,
            principal,
            translation_id=translation_id,
            request_id=request_id,
        )
    except DBAPIError as exc:
        raise ValueError("translation is not eligible for submission") from exc

    if result is None:
        raise ValueError("only the translation author can submit this translation")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.localization.submit_translation",
        resource_type="academy_translation_lineage",
        resource_id=str(translation_id),
        data={"workflow_event": "submitted"},
    )
    return result


async def decide_translation_review(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    translation_id: UUID,
    payload: TranslationReviewRequest,
) -> dict[str, Any]:
    try:
        result = await review_translation(
            session,
            principal,
            translation_id=translation_id,
            decision=payload.decision,
            reason=payload.reason,
            request_id=request_id,
        )
    except DBAPIError as exc:
        raise ValueError("translation review state conflict") from exc

    if result is None:
        raise ValueError("translator cannot review own translation or translation does not exist")

    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action=f"academy.localization.{payload.decision}_translation",
        resource_type="academy_translation_lineage",
        resource_id=str(translation_id),
        data={
            "workflow_event": payload.decision,
            "reason_recorded": bool(payload.reason),
        },
    )
    return result


async def translation_authority(
    session: AsyncSession,
    principal: Principal,
    *,
    content_id: UUID | None = None,
) -> list[dict[str, Any]]:
    return await list_translation_authority(
        session,
        principal,
        content_id=content_id,
    )
