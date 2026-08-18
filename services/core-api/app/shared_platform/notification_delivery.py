from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

DeliveryStatus = Literal["PENDING", "DELIVERED", "DEAD_LETTER"]
DigestMode = Literal["IMMEDIATE", "DAILY", "WEEKLY"]


@dataclass(frozen=True)
class DeliveryPolicy:
    max_attempts: int = 5
    base_backoff_seconds: int = 30
    max_backoff_seconds: int = 3600
    escalation_after_minutes: int | None = None
    digest_mode: DigestMode = "IMMEDIATE"


@dataclass(frozen=True)
class DeliveryState:
    status: DeliveryStatus = "PENDING"
    attempt_count: int = 0
    next_attempt_at: datetime | None = None
    delivered_at: datetime | None = None
    escalation_due: bool = False
    last_error: str | None = None


def _validate_policy(policy: DeliveryPolicy) -> None:
    if not 1 <= policy.max_attempts <= 20:
        raise ValueError("notification max attempts must be between 1 and 20")
    if (
        policy.base_backoff_seconds <= 0
        or policy.max_backoff_seconds < policy.base_backoff_seconds
    ):
        raise ValueError("notification retry backoff is invalid")
    if (
        policy.escalation_after_minutes is not None
        and policy.escalation_after_minutes <= 0
    ):
        raise ValueError("notification escalation delay must be positive")


def next_digest_delivery(*, now: datetime, mode: DigestMode) -> datetime:
    now = now.astimezone(UTC)
    if mode == "IMMEDIATE":
        return now
    if mode == "DAILY":
        tomorrow = (now + timedelta(days=1)).date()
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, tzinfo=UTC)
    if mode == "WEEKLY":
        days = 7 - now.weekday()
        monday = (now + timedelta(days=days)).date()
        return datetime(monday.year, monday.month, monday.day, 8, tzinfo=UTC)
    raise ValueError("unsupported digest mode")


def initialize_delivery(*, created_at: datetime, policy: DeliveryPolicy) -> DeliveryState:
    _validate_policy(policy)
    return DeliveryState(
        next_attempt_at=next_digest_delivery(now=created_at, mode=policy.digest_mode)
    )


def record_delivery_success(
    state: DeliveryState,
    *,
    delivered_at: datetime,
) -> DeliveryState:
    if state.status != "PENDING":
        raise ValueError("only pending notification can be delivered")
    return replace(
        state,
        status="DELIVERED",
        delivered_at=delivered_at.astimezone(UTC),
        next_attempt_at=None,
        last_error=None,
    )


def record_delivery_failure(
    state: DeliveryState,
    *,
    failed_at: datetime,
    created_at: datetime,
    policy: DeliveryPolicy,
    error: str,
) -> DeliveryState:
    _validate_policy(policy)
    if state.status != "PENDING":
        raise ValueError("only pending notification can fail")

    attempt = state.attempt_count + 1
    elapsed = failed_at.astimezone(UTC) - created_at.astimezone(UTC)
    escalation_due = (
        policy.escalation_after_minutes is not None
        and elapsed >= timedelta(minutes=policy.escalation_after_minutes)
    )
    if attempt >= policy.max_attempts:
        return replace(
            state,
            status="DEAD_LETTER",
            attempt_count=attempt,
            next_attempt_at=None,
            escalation_due=escalation_due,
            last_error=error,
        )

    backoff = min(
        policy.max_backoff_seconds,
        policy.base_backoff_seconds * (2 ** (attempt - 1)),
    )
    return replace(
        state,
        attempt_count=attempt,
        next_attempt_at=failed_at.astimezone(UTC) + timedelta(seconds=backoff),
        escalation_due=escalation_due,
        last_error=error,
    )
