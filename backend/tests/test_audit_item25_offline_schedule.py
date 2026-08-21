from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.audit.offline_schedule import (
    OfflineAuditError,
    create_schedule,
    issue_offline_package,
    materialize_occurrence,
    mutation,
    open_queue,
    reconcile_offline_mutations,
    seal_queue,
)
from app.modules.audit.template_authority import AuditTemplateRevision, AuditTemplateStatus


NOW = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)
SCHEDULE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PACKAGE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MUTATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
KEY = bytes.fromhex("11" * 32)
QUEUE_NONCE = bytes.fromhex("22" * 12)


def _template(revision=4, content_hash="1" * 64):
    return AuditTemplateRevision(
        tenant_id="tenant-a",
        template_key="store-safety",
        revision=revision,
        status=AuditTemplateStatus.PUBLISHED,
        questions=(),
        created_by="owner@example.com",
        created_at=NOW - timedelta(days=5),
        content_hash=content_hash,
        published_by="reviewer@example.com",
        published_at=NOW - timedelta(days=4),
    )


def _schedule():
    return create_schedule(
        _template(),
        schedule_key="weekly-safety",
        location_id="store-42",
        assignee_subject="auditor@example.com",
        window_start=NOW,
        window_end=NOW + timedelta(days=1),
        actor="audit-admin@example.com",
        created_at=NOW - timedelta(minutes=10),
        schedule_id=SCHEDULE_ID,
    )


def _package():
    occurrence = materialize_occurrence(_schedule(), scheduled_for=NOW + timedelta(hours=1))
    return issue_offline_package(
        occurrence,
        device_id="managed-device-7",
        assignee_subject="auditor@example.com",
        package_version="offline-v1",
        client_schema_version="audit-schema-v3",
        policy_version="audit-policy-v5",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=12),
        package_id=PACKAGE_ID,
    )


def _mutation(package, *, sequence=1, nonce="nonce-1", idem="idem-1", payload=None, mutation_id=MUTATION_ID):
    return mutation(
        package,
        sequence=sequence,
        nonce=nonce,
        idempotency_key=idem,
        mutation_type="answer",
        payload=payload or {"question_id": "q_fire_exit", "answer": "no"},
        captured_at=NOW + timedelta(hours=2),
        mutation_id=mutation_id,
    )


def test_scheduled_occurrence_is_deterministic_and_pins_assignment_and_template():
    schedule = _schedule()
    first = materialize_occurrence(schedule, scheduled_for=NOW + timedelta(hours=1))
    second = materialize_occurrence(schedule, scheduled_for=NOW + timedelta(hours=1))
    assert first.occurrence_id == second.occurrence_id
    assert first.occurrence_hash == second.occurrence_hash
    assert first.template_revision == 4
    assert first.template_hash == "1" * 64
    assert first.location_id == "store-42"
    assert first.assignee_subject == "auditor@example.com"


def test_eight_hour_offline_restart_round_trip_has_zero_queue_loss():
    package = _package()
    mutations = tuple(
        _mutation(
            package,
            sequence=index,
            nonce=f"nonce-{index}",
            idem=f"idem-{index}",
            mutation_id=UUID(f"00000000-0000-4000-8000-{index:012d}"),
            payload={"question_id": f"q{index}", "answer": index},
        )
        for index in range(1, 6)
    )
    sealed = seal_queue(mutations, key=KEY, package_hash=package.package_hash, nonce=QUEUE_NONCE)
    restored = open_queue(sealed, key=KEY, package_hash=package.package_hash)
    restored_after_restart = open_queue(sealed, key=KEY, package_hash=package.package_hash)
    assert restored == mutations
    assert restored_after_restart == mutations
    ledger, receipt = reconcile_offline_mutations(
        package,
        restored,
        principal_tenant_id="tenant-a",
        actor_subject="auditor@example.com",
        now=NOW + timedelta(hours=8),
    )
    assert len(ledger.accepted) == 5
    assert len(receipt.accepted_mutation_ids) == 5
    assert receipt.highest_sequence == 5


def test_twenty_replays_create_one_occurrence_run_and_one_mutation():
    package = _package()
    first = _mutation(package)
    ledger, first_receipt = reconcile_offline_mutations(
        package,
        [first],
        principal_tenant_id="tenant-a",
        actor_subject="auditor@example.com",
        now=NOW + timedelta(hours=3),
    )
    replays = [
        replace(first, mutation_id=UUID(f"10000000-0000-4000-8000-{index:012d}"))
        for index in range(1, 21)
    ]
    ledger2, replay_receipt = reconcile_offline_mutations(
        package,
        replays,
        principal_tenant_id="tenant-a",
        actor_subject="auditor@example.com",
        now=NOW + timedelta(hours=4),
        ledger=ledger,
    )
    assert ledger2.audit_run_id == first_receipt.audit_run_id == replay_receipt.audit_run_id
    assert len(ledger2.accepted) == 1
    assert replay_receipt.accepted_mutation_ids == ()
    assert len(replay_receipt.replayed_mutation_ids) == 20


def test_sync_fails_closed_on_tenant_assignment_device_sequence_and_nonce_conflicts():
    package = _package()
    first = _mutation(package)
    with pytest.raises(OfflineAuditError, match="principal tenant"):
        reconcile_offline_mutations(
            package, [first], principal_tenant_id="tenant-b",
            actor_subject="auditor@example.com", now=NOW + timedelta(hours=3)
        )
    with pytest.raises(OfflineAuditError, match="assignment"):
        reconcile_offline_mutations(
            package, [first], principal_tenant_id="tenant-a",
            actor_subject="other@example.com", now=NOW + timedelta(hours=3)
        )
    with pytest.raises(OfflineAuditError, match="device mismatch"):
        reconcile_offline_mutations(
            package, [replace(first, device_id="rogue-device")],
            principal_tenant_id="tenant-a", actor_subject="auditor@example.com",
            now=NOW + timedelta(hours=3)
        )
    with pytest.raises(OfflineAuditError, match="expected 1, got 2"):
        reconcile_offline_mutations(
            package, [replace(first, sequence=2)],
            principal_tenant_id="tenant-a", actor_subject="auditor@example.com",
            now=NOW + timedelta(hours=3)
        )

    ledger, _ = reconcile_offline_mutations(
        package, [first], principal_tenant_id="tenant-a",
        actor_subject="auditor@example.com", now=NOW + timedelta(hours=3)
    )
    second = _mutation(
        package, sequence=2, nonce=first.nonce, idem="idem-2",
        mutation_id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
    )
    with pytest.raises(OfflineAuditError, match="nonce reuse"):
        reconcile_offline_mutations(
            package, [second], principal_tenant_id="tenant-a",
            actor_subject="auditor@example.com", now=NOW + timedelta(hours=4), ledger=ledger
        )


def test_idempotency_key_cannot_replay_changed_payload():
    package = _package()
    first = _mutation(package)
    ledger, _ = reconcile_offline_mutations(
        package, [first], principal_tenant_id="tenant-a",
        actor_subject="auditor@example.com", now=NOW + timedelta(hours=3)
    )
    changed = _mutation(
        package,
        payload={"question_id": "q_fire_exit", "answer": "yes"},
        mutation_id=UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
    )
    with pytest.raises(OfflineAuditError, match="changed governed mutation content"):
        reconcile_offline_mutations(
            package, [changed], principal_tenant_id="tenant-a",
            actor_subject="auditor@example.com", now=NOW + timedelta(hours=4), ledger=ledger
        )


def test_new_template_revision_does_not_change_existing_occurrence_package():
    package = _package()
    newer = _template(revision=5, content_hash="9" * 64)
    assert newer.revision == 5
    assert package.template_revision == 4
    assert package.template_hash == "1" * 64
    assert package.client_schema_version == "audit-schema-v3"
    assert package.policy_version == "audit-policy-v5"


def test_capture_must_be_within_frozen_offline_package_validity():
    package = _package()
    late = replace(_mutation(package), captured_at=package.expires_at + timedelta(seconds=1))
    with pytest.raises(OfflineAuditError, match="outside package validity"):
        reconcile_offline_mutations(
            package, [late], principal_tenant_id="tenant-a",
            actor_subject="auditor@example.com", now=NOW + timedelta(hours=13)
        )
