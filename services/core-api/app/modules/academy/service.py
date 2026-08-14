from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.media import (
    AcademyMediaUnavailable,
    build_playback_url,
    issue_playback_token,
    load_media_config,
    media_unavailable_http,
)
from app.modules.academy.rag import grounded_document_answer
from app.modules.academy.repository import (
    claim_idempotency_key,
    get_blocking_checkpoint,
    get_completion_snapshot,
    get_media_asset,
    get_progress_snapshot,
    get_progress_target,
    get_quiz_attempt_by_id,
    get_quiz_definition_for_attempt,
    get_required_quiz_ids,
    is_completion_revoked,
    is_module_entitled,
    mark_enrollment_completed,
    record_learning_event,
    record_platform_audit,
    save_progress,
    save_quiz_attempt,
)
from app.modules.academy.repository_utils import stable_fingerprint


async def require_module(session: AsyncSession, principal: Principal) -> None:
    if not await is_module_entitled(session, principal.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Academy module entitlement is not active for this tenant",
        )


def _request_fingerprint(operation: str, value: object) -> str:
    return stable_fingerprint({"operation": operation, "payload": value})


def _required_watch_percent(target: dict[str, Any]) -> float:
    """Return the server-authoritative watch threshold for timed learning media."""

    if target.get("content_type") not in {"video", "live"}:
        return 0.0
    if int(target.get("duration_ms") or 0) <= 0:
        return 0.0

    policy = target.get("completion_policy")
    raw_value = policy.get("required_watch_percent", 90) if isinstance(policy, dict) else 90
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = 90.0
    return min(100.0, max(0.0, value))


async def update_progress(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    enrollment_id: UUID,
    payload: Any,
    idempotency_key: str | None,
) -> dict[str, Any]:
    await require_module(session, principal)
    fingerprint = _request_fingerprint(
        "academy.progress.v1",
        {"enrollment_id": enrollment_id, **payload.model_dump(mode="json")},
    )
    claim = await claim_idempotency_key(
        session,
        principal,
        operation="academy.progress.v1",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        resource_id=f"{enrollment_id}:{payload.content_version_id}",
    )
    if not claim["claimed"]:
        if claim["request_fingerprint"] != fingerprint:
            raise HTTPException(
                status_code=409, detail="Idempotency key was already used with a different request"
            )
        snapshot = await get_progress_snapshot(
            session, principal, enrollment_id, payload.content_version_id
        )
        if snapshot is None:
            raise HTTPException(
                status_code=409, detail="Idempotent progress result is no longer available"
            )
        return {**snapshot, "idempotent_replay": True}

    target = await get_progress_target(
        session, principal, enrollment_id, payload.content_version_id
    )
    if target is None:
        raise HTTPException(
            status_code=404, detail="Active Academy enrollment/content target not found"
        )

    current_revision = int(target["revision"])
    if payload.expected_revision is not None and payload.expected_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={"message": "Progress revision conflict", "current_revision": current_revision},
        )

    requested_position = payload.last_position_ms
    duration_ms = int(target["duration_ms"] or 0)
    if duration_ms and requested_position > duration_ms + 5000:
        raise HTTPException(status_code=400, detail="Progress position exceeds media duration")

    checkpoint = await get_blocking_checkpoint(
        session,
        principal,
        enrollment_id=enrollment_id,
        content_version_id=payload.content_version_id,
        requested_position_ms=requested_position,
    )
    if checkpoint:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Required video checkpoint must be completed before continuing",
                "quiz_id": str(checkpoint["quiz_id"]),
                "checkpoint_at_ms": checkpoint["checkpoint_at_ms"],
                "quiz_version": checkpoint["version_number"],
            },
        )

    watched_ms = int(target["watched_ms"]) + payload.watched_delta_ms
    if duration_ms:
        watched_ms = min(duration_ms, watched_ms)
    max_position_ms = max(int(target["max_position_ms"]), requested_position)
    if duration_ms:
        progress_percent = min(100.0, max_position_ms * 100.0 / duration_ms)
        watched_percent = min(100.0, watched_ms * 100.0 / duration_ms)
    else:
        progress_percent = (
            100.0 if payload.complete_requested else float(target["progress_percent"])
        )
        watched_percent = 100.0 if payload.complete_requested else 0.0

    required_watch_percent = _required_watch_percent(target)
    watched_requirement_met = watched_percent >= required_watch_percent
    completed = bool(
        payload.complete_requested
        and progress_percent >= 90.0
        and watched_requirement_met
    )
    progress_status = "completed" if completed else "in_progress"
    row = await save_progress(
        session,
        principal,
        enrollment_id,
        payload.content_version_id,
        status=progress_status,
        progress_percent=progress_percent,
        last_position_ms=requested_position,
        max_position_ms=max_position_ms,
        watched_ms=watched_ms,
        completed=completed,
        expected_revision=current_revision,
    )
    if row is None:
        raise HTTPException(
            status_code=409,
            detail={"message": "Progress revision conflict", "current_revision": current_revision},
        )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="progress_updated",
        enrollment_id=enrollment_id,
        content_version_id=payload.content_version_id,
        idempotency_key=idempotency_key,
        data={
            "revision": row["revision"],
            "progress_percent": float(row["progress_percent"]),
            "watched_percent": round(watched_percent, 2),
            "required_watch_percent": required_watch_percent,
        },
    )
    return {
        **row,
        "idempotent_replay": False,
        "watched_percent": round(watched_percent, 2),
        "required_watch_percent": required_watch_percent,
    }


async def submit_quiz_attempt(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    quiz_id: UUID,
    payload: Any,
    idempotency_key: str | None,
) -> dict[str, Any]:
    await require_module(session, principal)
    fingerprint = _request_fingerprint(
        "academy.quiz-attempt.v1",
        {"quiz_id": quiz_id, **payload.model_dump(mode="json")},
    )
    attempt_id = uuid4()
    claim = await claim_idempotency_key(
        session,
        principal,
        operation="academy.quiz-attempt.v1",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        resource_id=str(attempt_id),
    )
    if not claim["claimed"]:
        if claim["request_fingerprint"] != fingerprint:
            raise HTTPException(
                status_code=409, detail="Idempotency key was already used with a different request"
            )
        attempt = await get_quiz_attempt_by_id(session, principal, UUID(str(claim["resource_id"])))
        if attempt is None:
            raise HTTPException(
                status_code=409, detail="Idempotent quiz result is no longer available"
            )
        return {**attempt, "idempotent_replay": True}

    definition = await get_quiz_definition_for_attempt(
        session, principal, quiz_id, payload.enrollment_id
    )
    if definition is None:
        raise HTTPException(
            status_code=404, detail="Published quiz is not available for this enrollment"
        )
    if (
        definition["max_attempts"] is not None
        and definition["previous_attempts"] >= definition["max_attempts"]
    ):
        raise HTTPException(status_code=409, detail="Maximum quiz attempts reached")

    answer_map = {answer.question_id: set(answer.selected_option_ids) for answer in payload.answers}
    expected_questions = {question["question_id"] for question in definition["questions"]}
    if set(answer_map) != expected_questions:
        raise HTTPException(
            status_code=400, detail="Quiz answers must cover the exact published question set"
        )

    graded: list[dict[str, Any]] = []
    total_points = 0.0
    awarded = 0.0
    for question in definition["questions"]:
        selected = answer_map[question["question_id"]]
        if not selected.issubset(question["option_ids"]):
            raise HTTPException(
                status_code=400,
                detail="Quiz answer contains an option outside the published quiz version",
            )
        correct = selected == question["correct_option_ids"]
        points = float(question["points"])
        total_points += points
        awarded_points = points if correct else 0.0
        awarded += awarded_points
        graded.append(
            {
                "question_id": question["question_id"],
                "selected_option_ids": selected,
                "is_correct": correct,
                "awarded_points": awarded_points,
            }
        )
    score = round(100.0 * awarded / total_points, 2) if total_points else 0.0
    passed = score >= float(definition["pass_score"])
    attempt = await save_quiz_attempt(
        session,
        principal,
        attempt_id=attempt_id,
        quiz_id=quiz_id,
        enrollment_id=payload.enrollment_id,
        attempt_number=int(definition["previous_attempts"]) + 1,
        score=score,
        passed=passed,
        graded_answers=graded,
    )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="quiz_attempted",
        enrollment_id=payload.enrollment_id,
        content_version_id=definition["content_version_id"],
        quiz_id=quiz_id,
        idempotency_key=idempotency_key,
        data={"attempt_number": attempt["attempt_number"], "score": score, "passed": passed},
    )
    return {**attempt, "idempotent_replay": False}


async def complete_enrollment(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    enrollment_id: UUID,
) -> dict[str, Any]:
    await require_module(session, principal)
    snapshot = await get_completion_snapshot(session, principal, enrollment_id)
    if snapshot is None:
        if await is_completion_revoked(session, principal, enrollment_id):
            raise HTTPException(
                status_code=409,
                detail="Completion was revoked; a new enrollment/review is required",
            )
        raise HTTPException(status_code=404, detail="Academy enrollment not found")
    if snapshot["incomplete_content_version_ids"] or snapshot["missing_required_quiz_ids"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Completion requirements are not satisfied",
                "incomplete_content_version_ids": [
                    str(v) for v in snapshot["incomplete_content_version_ids"]
                ],
                "missing_required_quiz_ids": [
                    str(v) for v in snapshot["missing_required_quiz_ids"]
                ],
            },
        )
    if snapshot["certificate"] and snapshot["certificate"]["revoked_at"] is None:
        return {
            "enrollment_id": enrollment_id,
            "status": "completed",
            "certificate_code": snapshot["certificate"]["certificate_code"],
            "contract_version": snapshot["certificate"]["contract_version"],
            "completion_fingerprint": snapshot["certificate"]["completion_fingerprint"],
            "idempotent_replay": True,
        }

    required_quiz_ids = await get_required_quiz_ids(session, principal, snapshot["path_id"])
    completion_fingerprint = stable_fingerprint(
        {
            "contract": "academy-completion-v1",
            "tenant_id": principal.tenant_id,
            "subject": principal.subject,
            "enrollment_id": enrollment_id,
            "path_id": snapshot["path_id"],
            "required_content_version_ids": snapshot["required_content_version_ids"],
            "required_quiz_ids": required_quiz_ids,
        }
    )
    certificate_code = (
        f"EAY-{str(principal.tenant_id)[:8]}-{str(enrollment_id)[:8]}-{completion_fingerprint[:10]}"
    ).upper()
    certificate = await mark_enrollment_completed(
        session,
        principal,
        enrollment_id=enrollment_id,
        path_id=snapshot["path_id"],
        certificate_enabled=bool(snapshot["certificate_enabled"]),
        certificate_code=certificate_code,
        completion_fingerprint=completion_fingerprint,
    )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="enrollment_completed",
        enrollment_id=enrollment_id,
        data={"completion_fingerprint": completion_fingerprint},
    )
    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.enrollment.completed",
        resource_type="academy_enrollment",
        resource_id=str(enrollment_id),
        data={"completion_fingerprint": completion_fingerprint},
    )
    return {
        "enrollment_id": enrollment_id,
        "status": "completed",
        **certificate,
        "idempotent_replay": False,
    }


async def authorize_playback(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    media_id: UUID,
) -> dict[str, Any]:
    await require_module(session, principal)
    media = await get_media_asset(session, principal, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Accessible ready media asset not found")
    try:
        config = load_media_config()
        token, expires_at = issue_playback_token(
            config,
            principal,
            media_id=media_id,
            content_version_id=media["content_version_id"],
            delivery_key=media["delivery_key"],
        )
    except AcademyMediaUnavailable as exc:
        raise media_unavailable_http(exc) from exc
    playback_url = build_playback_url(
        config,
        delivery_key=media["delivery_key"],
        manifest_path=media["manifest_path"],
        token=token,
        delivery_mode=media["delivery_mode"],
    )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="playback_authorized",
        content_version_id=media["content_version_id"],
        data={"media_id": str(media_id), "expires_at": expires_at},
    )
    return {
        "playback_url": playback_url,
        "authorization_token": token,
        "expires_in_seconds": config.token_ttl_seconds,
        "content_version_id": media["content_version_id"],
        "cache_policy": "private-manifest, public-cacheable-segments-with-edge-auth",
        "download_protection": "friction-not-guarantee",
    }


async def answer_question(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    payload: Any,
) -> dict[str, Any]:
    await require_module(session, principal)
    result = await grounded_document_answer(
        session,
        principal,
        question=payload.question,
        locale=payload.locale,
        top_k=payload.top_k,
    )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="knowledge_question_answered",
        data={
            "supported": result["supported"],
            "mode": result["mode"],
            "source_version_ids": [str(item["content_version_id"]) for item in result["sources"]],
        },
    )
    return result
