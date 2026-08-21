from pathlib import Path


MIGRATION = Path("backend/migrations/006_field_intelligence.sql")


def test_field_migration_forces_rls_on_every_tenant_table():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in text
    assert "field_current_tenant()" in text
    assert "session_user" in text
    for table in (
        "field_missions",
        "field_mission_targets",
        "field_offline_events",
        "field_evidence_envelopes",
        "field_verifications",
        "field_notification_events",
        "field_audit",
    ):
        assert f"'{table}'" in text


def test_offline_evidence_verification_and_audit_are_append_only():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "field_offline_events_immutable BEFORE UPDATE OR DELETE" in text
    assert "field_evidence_immutable BEFORE UPDATE OR DELETE" in text
    assert "field_verifications_immutable BEFORE UPDATE OR DELETE" in text
    assert "field_audit_immutable BEFORE UPDATE OR DELETE" in text


def test_offline_and_notification_dispatch_have_tenant_scoped_idempotency():
    text = MIGRATION.read_text(encoding="utf-8")
    assert text.count("UNIQUE (tenant_id, idempotency_key)") >= 2
    assert "PRIMARY KEY (tenant_id, device_id, device_sequence)" in text
