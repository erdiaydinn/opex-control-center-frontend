from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.localization_schemas import (
    LocaleSettingUpdateRequest,
    TranslationLineageCreateRequest,
    TranslationReviewRequest,
)
from app.modules.academy.localization_service import (
    author_translation_lineage,
    configure_locale,
    decide_translation_review,
    localization_governance_telemetry,
    localization_settings,
    submit_translation_for_review,
    translation_authority,
)

router = APIRouter(prefix="/localization", tags=["academy-localization"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
LocalizationManager = Annotated[
    Principal,
    Depends(require_permission("action:academy:manageContent")),
]


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "academy-localization-untracked"))


def _domain_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    code = (
        status.HTTP_400_BAD_REQUEST
        if detail.startswith("unsupported")
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=code, detail=detail)


@router.get("/settings")
async def get_locale_settings(
    session: TenantSession,
    principal: LocalizationManager,
) -> dict[str, object]:
    items = await localization_settings(session, principal)
    return {"items": items, "count": len(items)}


@router.put("/settings/{locale}")
async def put_locale_setting(
    locale: str,
    payload: LocaleSettingUpdateRequest,
    request: Request,
    session: TenantSession,
    principal: LocalizationManager,
) -> dict[str, object]:
    try:
        return await configure_locale(
            session,
            principal,
            request_id=_request_id(request),
            locale=locale,
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.get("/translations")
async def get_translation_authority(
    session: TenantSession,
    principal: LocalizationManager,
    content_id: UUID | None = None,
) -> dict[str, object]:
    items = await translation_authority(
        session,
        principal,
        content_id=content_id,
    )
    return {"items": items, "count": len(items)}


@router.get("/telemetry")
async def get_localization_governance_telemetry(
    session: TenantSession,
    principal: LocalizationManager,
) -> dict[str, object]:
    return await localization_governance_telemetry(session, principal)


@router.post("/translations", status_code=status.HTTP_201_CREATED)
async def post_translation_lineage(
    payload: TranslationLineageCreateRequest,
    request: Request,
    session: TenantSession,
    principal: LocalizationManager,
) -> dict[str, object]:
    try:
        return await author_translation_lineage(
            session,
            principal,
            request_id=_request_id(request),
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.post("/translations/{translation_id}/submit")
async def post_translation_submit(
    translation_id: UUID,
    request: Request,
    session: TenantSession,
    principal: LocalizationManager,
) -> dict[str, object]:
    try:
        return await submit_translation_for_review(
            session,
            principal,
            request_id=_request_id(request),
            translation_id=translation_id,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.post("/translations/{translation_id}/review")
async def post_translation_review(
    translation_id: UUID,
    payload: TranslationReviewRequest,
    request: Request,
    session: TenantSession,
    principal: LocalizationManager,
) -> dict[str, object]:
    try:
        return await decide_translation_review(
            session,
            principal,
            request_id=_request_id(request),
            translation_id=translation_id,
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc
