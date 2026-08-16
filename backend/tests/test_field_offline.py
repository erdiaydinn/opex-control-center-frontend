from datetime import datetime, timezone

from app.modules.field_intelligence.offline import (
    ExistingOfflineEvent,
    OfflineEvent,
    OfflineSyncDecision,
    reconcile_offline_event,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def event(payload="a" * 64, key="mission-1-device-1-42"):
    return OfflineEvent(
        tenant_id="tenant-a",
        mission_id="mission-1",
        location_id="store-1",
        actor_id="employee-1",
        device_id="device-1",
        device_sequence=42,
        idempotency_key=key,
        payload_hash=payload,
        captured_at=NOW,
    )


def existing(payload="a" * 64, key="mission-1-device-1-42"):
    return ExistingOfflineEvent(
        tenant_id="tenant-a",
        device_id="device-1",
        device_sequence=42,
        idempotency_key=key,
        payload_hash=payload,
    )


def test_new_offline_sequence_is_accepted():
    assert reconcile_offline_event(event(), None).decision is OfflineSyncDecision.ACCEPT


def test_exact_reconnect_replay_is_idempotent():
    assert reconcile_offline_event(event(), existing()).decision is OfflineSyncDecision.IDEMPOTENT_REPLAY


def test_same_device_sequence_with_changed_payload_fails_closed():
    result = reconcile_offline_event(event(payload="b" * 64), existing())
    assert result.decision is OfflineSyncDecision.CONFLICT
    assert "different payload" in result.reason


def test_same_sequence_with_changed_idempotency_key_fails_closed():
    result = reconcile_offline_event(event(key="mission-1-device-1-other"), existing())
    assert result.decision is OfflineSyncDecision.CONFLICT
