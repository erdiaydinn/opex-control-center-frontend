from pathlib import Path


MIGRATION = Path("backend/migrations/007_business_glossary.sql")


def test_glossary_uses_null_safe_scope_uniqueness_and_forced_rls():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "NULLS NOT DISTINCT" in text
    assert "FORCE ROW LEVEL SECURITY" in text
    assert "glossary_current_tenant()" in text
    assert "session_user" in text


def test_effective_definition_requires_new_version_for_content_change():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "glossary_definition_guard BEFORE UPDATE" in text
    assert "effective glossary definition is immutable; create a new version" in text
    assert "effective glossary status may only remain effective or become superseded" in text


def test_governance_events_are_append_only():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "glossary_governance_immutable BEFORE UPDATE OR DELETE" in text
