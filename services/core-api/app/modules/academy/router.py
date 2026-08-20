from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.localization import RTL_LOCALES, SUPPORTED_LOCALES
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.admin_router import router as admin_router
from app.modules.academy.experience_router import router as experience_router
from app.modules.academy.localization_router import router as localization_router
from app.modules.academy.progress_service import update_progress
from app.modules.academy.repository import (
    create_content,
    create_content_version,
    create_learning_path,
    create_manual_enrollment,
    create_media_asset,
    create_quiz,
    get_enrollment_workspace,
    get_quiz_public_definition,
    grant_entitlement,
    ingest_document_chunks,
    list_certificates,
    list_checkpoints,
    list_enrollments,
    list_entitled_content,
    reconcile_role_enrollments,
    record_platform_audit,
    revoke_completion,
)
from app.modules.academy.schemas import (
    CertificateRevocationRequest,
    ContentCreateRequest,
    ContentVersionCreateRequest,
    DocumentIngestRequest,
    EntitlementCreateRequest,
    LearningPathCreateRequest,
    ManualEnrollmentRequest,
    MediaAssetCreateRequest,
    ProgressUpdateRequest,
    QuestionAnswerRequest,
    QuizAttemptRequest,
    QuizCreateRequest,
)
from app.modules.academy.service import (
    answer_question,
    authorize_playback,
    complete_enrollment,
    require_module,
    submit_quiz_attempt,
)

router = APIRouter(prefix="/v1/academy", tags=["academy"])
router.include_router(admin_router)
router.include_router(experience_router)
router.include_router(localization_router)

TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Viewer = Annotated[Principal, Depends(require_permission("module:academy:view"))]
ManageContent = Annotated[
    Principal, Depends(require_permission("action:academy:manageContent"))
]
ManagePaths = Annotated[
    Principal, Depends(require_permission("action:academy:managePaths"))
]
ManageQuizzes = Annotated[
    Principal, Depends(require_permission("action:academy:manageQuizzes"))
]
ManageEntitlements = Annotated[
    Principal, Depends(require_permission("action:academy:manageEntitlements"))
]
AssignEnrollment = Annotated[
    Principal, Depends(require_permission("action:academy:assignEnrollment"))
]
IngestDocuments = Annotated[
    Principal, Depends(require_permission("action:academy:ingestDocuments"))
]
RevokeCompletion = Annotated[
    Principal, Depends(require_permission("action:academy:revokeCompletion"))
]


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "academy-untracked"))


@router.get("/me")
async def academy_home(session: TenantSession, principal: Viewer) -> dict[str, object]:
    await require_module(session, principal)
    await reconcile_role_enrollments(session, principal)
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "locales": list(SUPPORTED_LOCALES),
        "direction_by_locale": {
            locale: ("rtl" if locale in RTL_LOCALES else "ltr")
            for locale in SUPPORTED_LOCALES
        },
        "enrollments": await list_enrollments(session, principal),
        "content": await list_entitled_content(session, principal),
        "certificates": await list_certificates(session, principal),
    }


@router.post("/enrollments/reconcile")
async def reconcile_enrollments(session: TenantSession, principal: Viewer) -> dict[str, object]:
    await require_module(session, principal)
    created = await reconcile_role_enrollments(session, principal)
    return {"created": created, "enrollments": await list_enrollments(session, principal)}


@router.get("/enrollments/{enrollment_id}")
async def get_enrollment(
    enrollment_id: UUID,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await get_enrollment_workspace(session, principal, enrollment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Academy enrollment not found")
    return result


@router.patch("/enrollments/{enrollment_id}/progress")
async def patch_progress(
    enrollment_id: UUID,
    payload: ProgressUpdateRequest,
    request: Request,
    session: TenantSession,
    principal: Viewer,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    return await update_progress(
        session,
        principal,
        request_id=_request_id(request),
        enrollment_id=enrollment_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.get("/enrollments/{enrollment_id}/content/{content_version_id}/checkpoints")
async def get_checkpoints(
    enrollment_id: UUID,
    content_version_id: UUID,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    await require_module(session, principal)
    return {"items": await list_checkpoints(session, principal, enrollment_id, content_version_id)}


@router.get("/enrollments/{enrollment_id}/quizzes/{quiz_id}")
async def get_quiz(
    enrollment_id: UUID,
    quiz_id: UUID,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    await require_module(session, principal)
    definition = await get_quiz_public_definition(session, principal, quiz_id, enrollment_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Published quiz not found")
    return definition


@router.post("/quizzes/{quiz_id}/attempts", status_code=status.HTTP_201_CREATED)
async def post_quiz_attempt(
    quiz_id: UUID,
    payload: QuizAttemptRequest,
    request: Request,
    session: TenantSession,
    principal: Viewer,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    return await submit_quiz_attempt(
        session,
        principal,
        request_id=_request_id(request),
        quiz_id=quiz_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.post("/enrollments/{enrollment_id}/complete")
async def post_complete(
    enrollment_id: UUID,
    request: Request,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    return await complete_enrollment(
        session, principal, request_id=_request_id(request), enrollment_id=enrollment_id
    )


@router.post("/media/{media_id}/playback-authorization")
async def post_playback_authorization(
    media_id: UUID,
    request: Request,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    return await authorize_playback(
        session, principal, request_id=_request_id(request), media_id=media_id
    )


@router.post("/knowledge/answer")
async def post_knowledge_answer(
    payload: QuestionAnswerRequest,
    request: Request,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    return await answer_question(
        session, principal, request_id=_request_id(request), payload=payload
    )


@router.post("/admin/content", status_code=status.HTTP_201_CREATED)
async def post_content(
    payload: ContentCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManageContent,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await create_content(session, principal, payload)
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.content.created",
        resource_type="academy_content",
        resource_id=str(result["content"]["id"]),
        data={"content_version_id": str(result["version"]["id"])},
    )
    return result


@router.post("/admin/content/{content_id}/versions", status_code=status.HTTP_201_CREATED)
async def post_content_version(
    content_id: UUID,
    payload: ContentVersionCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManageContent,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await create_content_version(session, principal, content_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Academy content not found")
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.content.version.created",
        resource_type="academy_content_version",
        resource_id=str(result["id"]),
        data={"content_id": str(content_id), "version_number": result["version_number"]},
    )
    return result


@router.post("/admin/media", status_code=status.HTTP_201_CREATED)
async def post_media(
    payload: MediaAssetCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManageContent,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await create_media_asset(session, principal, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.media.created",
        resource_type="academy_media",
        resource_id=str(result["id"]),
        data={
            "content_version_id": str(result["content_version_id"]),
            "delivery_mode": result["delivery_mode"],
        },
    )
    return result


@router.post("/admin/paths", status_code=status.HTTP_201_CREATED)
async def post_path(
    payload: LearningPathCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManagePaths,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        result = await create_learning_path(session, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.path.created",
        resource_type="academy_learning_path",
        resource_id=str(result["id"]),
        data={},
    )
    return result


@router.post("/admin/quizzes", status_code=status.HTTP_201_CREATED)
async def post_quiz(
    payload: QuizCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManageQuizzes,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        result = await create_quiz(session, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.quiz.created",
        resource_type="academy_quiz",
        resource_id=str(result["id"]),
        data={"quiz_version": result["version_number"]},
    )
    return result


@router.post("/admin/entitlements", status_code=status.HTTP_201_CREATED)
async def post_entitlement(
    payload: EntitlementCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManageEntitlements,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await grant_entitlement(session, principal, payload)
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.entitlement.changed",
        resource_type="academy_entitlement",
        resource_id=str(result["id"]),
        data={"resource_type": result["resource_type"], "permission": result["permission"]},
    )
    return result


@router.post("/admin/enrollments", status_code=status.HTTP_201_CREATED)
async def post_manual_enrollment(
    payload: ManualEnrollmentRequest,
    request: Request,
    session: TenantSession,
    principal: AssignEnrollment,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await create_manual_enrollment(
        session, principal, path_id=payload.path_id, subject=payload.subject, due_at=payload.due_at
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Published learning path not found")
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.enrollment.assigned",
        resource_type="academy_enrollment",
        resource_id=str(result["id"]),
        data={"source": "manual"},
    )
    return result


@router.post("/admin/documents/ingest")
async def post_document_ingest(
    payload: DocumentIngestRequest,
    request: Request,
    session: TenantSession,
    principal: IngestDocuments,
) -> dict[str, object]:
    await require_module(session, principal)
    try:
        count = await ingest_document_chunks(session, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.document.ingested",
        resource_type="academy_content_version",
        resource_id=str(payload.content_version_id),
        data={"chunk_count": count},
    )
    return {"content_version_id": payload.content_version_id, "chunk_count": count}


@router.post("/admin/enrollments/{enrollment_id}/revoke-completion")
async def post_revoke_completion(
    enrollment_id: UUID,
    payload: CertificateRevocationRequest,
    request: Request,
    session: TenantSession,
    principal: RevokeCompletion,
) -> dict[str, object]:
    await require_module(session, principal)
    result = await revoke_completion(
        session, principal, enrollment_id=enrollment_id, reason=payload.reason
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Only completed enrollments can be revoked")
    await record_platform_audit(
        session,
        principal,
        request_id=_request_id(request),
        action="academy.completion.revoked",
        resource_type="academy_enrollment",
        resource_id=str(enrollment_id),
        data={"reason_sha256": __import__("hashlib").sha256(payload.reason.encode()).hexdigest()},
    )
    return result
