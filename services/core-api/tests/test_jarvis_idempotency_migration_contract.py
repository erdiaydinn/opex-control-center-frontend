from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0010_jarvis_execution_idempotency.py"
)


def source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_idempotency_table_has_tenant_rls_and_runtime_grants() -> None:
    text = source()

    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "FORCE ROW LEVEL SECURITY" in text
    assert "app.tenant_id" in text
    assert "WITH CHECK" in text
    assert "REVOKE ALL ON TABLE" in text
    assert "FROM PUBLIC" in text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in text
    assert "TO {RUNTIME_ROLE}" in text


def test_idempotency_uniqueness_is_tenant_actor_and_client_key_hash() -> None:
    text = source()

    assert '"tenant_id"' in text
    assert '"actor_subject_sha256"' in text
    assert '"idempotency_key_sha256"' in text
    assert "uq_jarvis_idempotency_actor_key" in text


def test_idempotency_schema_never_persists_raw_authority_or_result_data() -> None:
    text = source()

    forbidden_columns = (
        '"actor_subject",',
        '"idempotency_key",',
        '"grant_token",',
        '"arguments",',
        '"reason",',
        '"rows",',
        '"result",',
    )
    for forbidden in forbidden_columns:
        assert forbidden not in text


def test_idempotency_state_machine_is_database_constrained() -> None:
    text = source()

    for state in (
        "reserved",
        "dispatched",
        "completed",
        "indeterminate",
        "denied",
    ):
        assert state in text
    assert "ck_jarvis_idempotency_state" in text
