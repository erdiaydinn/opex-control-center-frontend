from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_authoring import (
    create_content,
    create_learning_path,
    create_quiz,
    grant_entitlement,
)
from app.modules.academy.repository_catalog import (
    get_media_asset,
    list_enrollments,
    list_entitled_content,
    reconcile_role_enrollments,
)
from app.modules.academy.repository_completion import (
    get_completion_snapshot,
    mark_enrollment_completed,
)
from app.modules.academy.repository_entitlement import is_module_entitled
from app.modules.academy.repository_idempotency_claim import claim_idempotency_key
from app.modules.academy.repository_progress import (
    get_progress_snapshot,
    get_progress_target,
    save_progress,
)
from app.modules.academy.repository_quiz import (
    get_quiz_attempt_by_id,
    get_quiz_definition_for_attempt,
    save_quiz_attempt,
)
from app.modules.academy.repository_utils import json_text


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
        text(
            """
            INSERT INTO academy_learning_events (
                tenant_id, subject, actor_subject, event_type,
                enrollment_id, content_version_id, quiz_id,
                idempotency_key, request_id, data
            )
            VALUES (
                :tenant_id, :subject, :actor_subject, :event_type,
                :enrollment_id, :content_version_id, :quiz_id,
                :idempotency_key, :request_id, CAST(:data AS jsonb)
            )
            ON CONFLICT (tenant_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
            DO NOTHING
            """
        ),
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
    await session.execute(
        text(
            """
            INSERT INTO audit_events (
                tenant_id, actor_subject, action, resource_type,
                resource_id, decision, request_id, data
            )
            VALUES (
                :tenant_id, :actor_subject, :action, :resource_type,
                :resource_id, 'allowed', :request_id, CAST(:data AS jsonb)
            )
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "actor_subject": principal.subject,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "request_id": request_id,
            "data": json_text(data or {}),
        },
    )


__all__ = [
    "claim_idempotency_key",
    "create_content",
    "create_learning_path",
    "create_quiz",
    "get_completion_snapshot",
    "get_media_asset",
    "get_progress_snapshot",
    "get_progress_target",
    "get_quiz_attempt_by_id",
    "get_quiz_definition_for_attempt",
    "grant_entitlement",
    "is_module_entitled",
    "list_enrollments",
    "list_entitled_content",
    "mark_enrollment_completed",
    "reconcile_role_enrollments",
    "record_learning_event",
    "record_platform_audit",
    "save_progress",
    "save_quiz_attempt",
]
