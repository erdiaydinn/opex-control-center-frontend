from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_transactional_audit_event
from app.core.security import Principal
from app.modules.academy.repository_admin import (
    academy_admin_summary,
    list_admin_content,
    list_admin_paths,
)
from app.modules.academy.repository_catalog import (
    get_media_asset,
    get_quiz_public_definition,
    list_checkpoints,
    list_entitled_content,
)
from app.modules.academy.repository_certificate import (
    get_required_quiz_ids,
    is_completion_revoked,
    list_certificates,
    revoke_completion,
)
from app.modules.academy.repository_completion import (
    get_completion_snapshot,
    mark_enrollment_completed,
)
from app.modules.academy.repository_content import (
    create_content,
    create_content_version,
    create_media_asset,
)
from app.modules.academy.repository_enrollment import (
    create_manual_enrollment,
    get_enrollment_workspace,
    list_enrollments,
    reconcile_role_enrollments,
)
from app.modules.academy.repository_entitlement import is_module_entitled
from app.modules.academy.repository_idempotency_claim import claim_idempotency_key
from app.modules.academy.repository_knowledge import ingest_document_chunks
from app.modules.academy.repository_path import create_learning_path, grant_entitlement
from app.modules.academy.repository_progress import (
    get_blocking_checkpoint,
    get_progress_snapshot,
    get_progress_target,
    save_progress,
)
from app.modules.academy.repository_quiz import (
    get_quiz_attempt_by_id,
    get_quiz_definition_for_attempt,
    save_quiz_attempt,
)
from app.modules.academy.repository_quiz_authoring import create_quiz
from app.modules.academy.repository_utils import json_text

__all__ = (
    "academy_admin_summary",
    "claim_idempotency_key",
    "create_content",
    "create_content_version",
    "create_learning_path",
    "create_manual_enrollment",
    "create_media_asset",
    "create_quiz",
    "get_blocking_checkpoint",
    "get_completion_snapshot",
    "get_enrollment_workspace",
    "get_media_asset",
    "get_progress_snapshot",
    "get_progress_target",
    "get_quiz_attempt_by_id",
    "get_quiz_definition_for_attempt",
    "get_quiz_public_definition",
    "get_required_quiz_ids",
    "grant_entitlement",
    "ingest_document_chunks",
    "is_completion_revoked",
    "is_module_entitled",
    "list_admin_content",
    "list_admin_paths",
    "list_certificates",
    "list_checkpoints",
    "list_entitled_content",
    "list_enrollments",
    "mark_enrollment_completed",
    "reconcile_role_enrollments",
    "record_learning_event",
    "record_platform_audit",
    "revoke_completion",
    "save_progress",
    "save_quiz_attempt",
)


async def record_learning_event(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    event_type: str,
    subject: str | None = None,
    enrollment_id: UUID | None = None,
    content_version_id: UUID | None = None,
    quiz_id: UUID | None = None,
    idempotency_key: str | None = None,
    data: dict[str, object] | None = None,
) -> None:
    await session.execute(
        text("""
        INSERT INTO academy_learning_events (
            tenant_id, subject, actor_subject, event_type, enrollment_id,
            content_version_id, quiz_id, idempotency_key, request_id, data
        ) VALUES (
            :tenant_id, :subject, :actor_subject, :event_type, :enrollment_id,
            :content_version_id, :quiz_id, :idempotency_key, :request_id,
            CAST(:data AS jsonb)
        )
        ON CONFLICT (tenant_id, idempotency_key)
            WHERE idempotency_key IS NOT NULL
        DO NOTHING
    """),
        {
            "tenant_id": principal.tenant_id,
            "subject": subject or principal.subject,
            "actor_subject": principal.subject,
            "event_type": event_type,
            "enrollment_id": enrollment_id,
            "content_version_id": content_version_id,
            "quiz_id": quiz_id,
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "data": json_text(data or {}),
        },
    )


async def record_platform_audit(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    data: dict[str, object] | None = None,
) -> None:
    await write_transactional_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_subject=principal.subject,
        request_id=request_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        data=data,
    )
