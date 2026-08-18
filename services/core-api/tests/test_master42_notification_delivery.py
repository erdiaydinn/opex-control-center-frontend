from datetime import UTC, datetime, timedelta

import pytest

from app.shared_platform.notification_delivery import (
    DeliveryPolicy,
    initialize_delivery,
    next_digest_delivery,
    record_delivery_failure,
    record_delivery_success,
)

BASE = datetime(2026, 8, 18, 10, tzinfo=UTC)


def test_retry_is_bounded_exponential_and_dead_letters() -> None:
    policy = DeliveryPolicy(
        max_attempts=3,
        base_backoff_seconds=10,
        max_backoff_seconds=60,
        escalation_after_minutes=1,
    )
    state = initialize_delivery(created_at=BASE, policy=policy)
    state = record_delivery_failure(
        state,
        failed_at=BASE,
        created_at=BASE,
        policy=policy,
        error="timeout",
    )
    assert state.attempt_count == 1
    assert state.next_attempt_at == BASE + timedelta(seconds=10)
    assert not state.escalation_due

    state = record_delivery_failure(
        state,
        failed_at=BASE + timedelta(seconds=70),
        created_at=BASE,
        policy=policy,
        error="timeout",
    )
    assert state.attempt_count == 2
    assert state.escalation_due

    state = record_delivery_failure(
        state,
        failed_at=BASE + timedelta(seconds=100),
        created_at=BASE,
        policy=policy,
        error="timeout",
    )
    assert state.status == "DEAD_LETTER"
    assert state.next_attempt_at is None
    with pytest.raises(ValueError, match="pending notification"):
        record_delivery_success(
            state,
            delivered_at=BASE + timedelta(seconds=101),
        )


def test_daily_and_weekly_digest_are_deterministic_utc_boundaries() -> None:
    assert next_digest_delivery(now=BASE, mode="DAILY") == datetime(
        2026,
        8,
        19,
        8,
        tzinfo=UTC,
    )
    weekly = next_digest_delivery(now=BASE, mode="WEEKLY")
    assert weekly.weekday() == 0
    assert weekly.hour == 8
    assert weekly > BASE


def test_success_is_terminal_and_clears_retry_state() -> None:
    state = initialize_delivery(created_at=BASE, policy=DeliveryPolicy())
    done = record_delivery_success(
        state,
        delivered_at=BASE + timedelta(seconds=5),
    )
    assert done.status == "DELIVERED"
    assert done.next_attempt_at is None
    with pytest.raises(ValueError, match="pending notification"):
        record_delivery_failure(
            done,
            failed_at=BASE + timedelta(seconds=10),
            created_at=BASE,
            policy=DeliveryPolicy(),
            error="late",
        )
