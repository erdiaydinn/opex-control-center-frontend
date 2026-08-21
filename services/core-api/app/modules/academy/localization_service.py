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
from app.modules.academy.repository_admin import academy_admin_summary
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


def _latest_default_sources(
    content_versions: list[dict[str, Any]],
    default_locale: str,
) -> list[dict[str, Any]]:
    latest: dict[object, dict[str, Any]] = {}
    for item in content_versions:
        if item.get("locale") != default_locale:
            continue
        if item.get("version_status") != "published" or item.get("content_status") != "published":
            continue
        content_id = item.get("content_id")
        if content_id is None:
            continue
        candidate = latest.get(content_id)
        if candidate is None or int(item.get("version_number") or 0) > int(candidate.get("version_number") or 0):
            latest[content_id] = item
    return list(latest.values())


def _coverage_percent(authoritative: int, source_count: int) -> float:
    if source_count <= 0:
        return 100.0
    return round((authoritative / source_count) * 100.0, 1)


async def localization_governance_telemetry(
    session: AsyncSession,
    principal: Principal,
) -> dict[str, Any]:
    """Derive localization governance telemetry from existing Academy authorities.

    This read model deliberately does not invent a linguistic quality score. It
    reports authority coverage, stale/source-change state, review workflow and
    machine-draft exposure from the existing locale, version and translation
    authorities.
    """

    settings = await list_locale_settings(session, principal)
    authority = await list_translation_authority(session, principal)
    workspace = await academy_admin_summary(session, principal)

    default_setting = next(
        (item for item in settings if item.get("enabled") and item.get("is_default")),
        None,
    )
    default_locale = str(default_setting.get("locale")) if default_setting else None
    content_versions = list(workspace.get("authoring", {}).get("content_versions", []))
    sources = _latest_default_sources(content_versions, default_locale) if default_locale else []

    locale_rows: list[dict[str, Any]] = []
    for setting in settings:
        target_locale = str(setting.get("locale") or "")
        if not setting.get("enabled") or setting.get("is_default") or not target_locale:
            continue

        current_by_content: dict[object, list[dict[str, Any]]] = {}
        for source in sources:
            content_id = source.get("content_id")
            source_version_id = source.get("content_version_id")
            matches = [
                row
                for row in authority
                if row.get("content_id") == content_id
                and row.get("source_version_id") == source_version_id
                and row.get("target_locale") == target_locale
            ]
            current_by_content[content_id] = matches

        lineage_count = sum(1 for rows in current_by_content.values() if rows)
        authoritative_count = sum(
            1 for rows in current_by_content.values() if any(bool(row.get("authoritative")) for row in rows)
        )
        pending_review_count = sum(
            1
            for rows in current_by_content.values()
            if any(row.get("workflow_status") == "submitted" and not row.get("stale") for row in rows)
        )
        machine_draft_count = sum(
            1
            for rows in current_by_content.values()
            if any(row.get("translation_method") == "machine_draft" and not row.get("stale") for row in rows)
        )
        historical = [row for row in authority if row.get("target_locale") == target_locale]
        stale_count = sum(1 for row in historical if row.get("stale"))
        rejected_count = sum(1 for row in historical if row.get("workflow_status") == "rejected")
        source_count = len(sources)

        locale_rows.append(
            {
                "locale": target_locale,
                "required": bool(setting.get("required")),
                "allow_machine_draft": bool(setting.get("allow_machine_draft")),
                "source_content_count": source_count,
                "lineage_content_count": lineage_count,
                "authoritative_content_count": authoritative_count,
                "missing_lineage_count": max(0, source_count - lineage_count),
                "authority_gap_count": max(0, source_count - authoritative_count),
                "pending_review_count": pending_review_count,
                "stale_translation_count": stale_count,
                "rejected_translation_count": rejected_count,
                "machine_draft_content_count": machine_draft_count,
                "coverage_percent": _coverage_percent(authoritative_count, source_count),
            }
        )

    required_rows = [row for row in locale_rows if row["required"]]
    required_slots = sum(int(row["source_content_count"]) for row in required_rows)
    required_authoritative = sum(int(row["authoritative_content_count"]) for row in required_rows)

    return {
        "source_locale": default_locale,
        "source_content_count": len(sources),
        "summary": {
            "enabled_target_locale_count": len(locale_rows),
            "required_target_locale_count": len(required_rows),
            "required_authority_slot_count": required_slots,
            "required_authoritative_slot_count": required_authoritative,
            "required_authority_gap_count": max(0, required_slots - required_authoritative),
            "required_coverage_percent": _coverage_percent(required_authoritative, required_slots),
            "stale_translation_count": sum(int(row["stale_translation_count"]) for row in locale_rows),
            "pending_review_count": sum(int(row["pending_review_count"]) for row in locale_rows),
            "rejected_translation_count": sum(int(row["rejected_translation_count"]) for row in locale_rows),
            "machine_draft_content_count": sum(int(row["machine_draft_content_count"]) for row in locale_rows),
        },
        "locales": locale_rows,
        "quality_score": None,
        "quality_score_reason": "not_computed_without_linguistic_qa_evidence",
    }
