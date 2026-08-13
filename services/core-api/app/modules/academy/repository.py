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
from app.modules.academy.repository_common import (
    claim_idempotency_key,
    complete_idempotency_key,
    is_module_entitled,
    record_learning_event,
    record_platform_audit,
)
from app.modules.academy.repository_completion import (
    get_completion_snapshot,
    mark_enrollment_completed,
)
from app.modules.academy.repository_progress import (
    get_progress_target,
    save_progress,
)
from app.modules.academy.repository_quiz import (
    get_quiz_definition_for_attempt,
    save_quiz_attempt,
)

__all__ = [
    "claim_idempotency_key",
    "complete_idempotency_key",
    "create_content",
    "create_learning_path",
    "create_quiz",
    "get_completion_snapshot",
    "get_media_asset",
    "get_progress_target",
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
