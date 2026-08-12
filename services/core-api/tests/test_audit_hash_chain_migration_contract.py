from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0011_audit_hash_chain.py"
)


def migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def function_block(source: str, function_name: str, next_marker: str) -> str:
    start = source.index(f"CREATE FUNCTION public.{function_name}")
    end = source.index(next_marker, start)
    return source[start:end]


def test_revision_is_linear_after_jarvis_idempotency() -> None:
    source = migration_text()
    assert 'revision: str = "0011_audit_hash_chain"' in source
    assert 'down_revision: str | None = "0010_jarvis_idempotency"' in source


def test_chain_columns_and_constraints_are_server_enforced() -> None:
    source = migration_text()
    for column in (
        "chain_sequence",
        "previous_event_hash",
        "event_hash",
        "event_payload",
    ):
        assert column in source
        assert f"ALTER COLUMN {column} SET NOT NULL" in source

    assert "chain_sequence > 0" in source
    assert "previous_event_hash ~ '^[0-9a-f]{64}$'" in source
    assert "event_hash ~ '^[0-9a-f]{64}$'" in source
    assert "uq_audit_events_tenant_chain_sequence" in source
    assert "uq_audit_events_tenant_event_hash" in source


def test_backfill_is_exclusive_rls_safe_and_restores_protections() -> None:
    source = migration_text()
    lock = source.index("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    no_force = source.index(
        "ALTER TABLE public.audit_events NO FORCE ROW LEVEL SECURITY"
    )
    disable = source.index(
        "ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_append_only"
    )
    backfill = source.index("UPDATE public.audit_events")
    enable = source.index(
        "ALTER TABLE public.audit_events ENABLE TRIGGER audit_events_append_only"
    )
    force = source.index("ALTER TABLE public.audit_events FORCE ROW LEVEL SECURITY")

    assert lock < no_force < disable < backfill < enable < force
    assert "ORDER BY created_at, id" in source
    assert "SELECT DISTINCT tenant_id" in source


def test_nullable_resource_id_does_not_make_payload_function_strict() -> None:
    source = migration_text()
    payload = function_block(
        source,
        "audit_event_payload_v1(",
        "CREATE FUNCTION public.audit_event_hash_v1(",
    )
    assert "p_resource_id text" in payload
    assert "'resource_id', p_resource_id" in payload
    assert "STRICT" not in payload


def test_hash_function_is_fixed_canonical_sha256_contract() -> None:
    source = migration_text()
    block = function_block(
        source,
        "audit_event_hash_v1(",
        "# The existing append-only trigger",
    )
    assert "IMMUTABLE" in block
    assert "STRICT" in block
    assert "SET search_path = pg_catalog, public" in block
    assert "eay-audit-chain-v1|" in block
    assert "public.digest(" in block
    assert "'sha256'" in block
    assert "'hex'" in block


def test_sealer_is_invoker_rights_fixed_path_and_has_no_dynamic_sql() -> None:
    source = migration_text()
    block = function_block(
        source,
        "seal_audit_event_v1()",
        "CREATE TRIGGER audit_events_hash_chain",
    )
    assert "SECURITY DEFINER" not in block
    assert "SET search_path = pg_catalog, public" in block
    assert "EXECUTE " not in block
    assert "pg_advisory_xact_lock" in block
    assert "WHERE tenant_id = NEW.tenant_id" in block
    assert "ORDER BY chain_sequence DESC" in block
    assert "audit chain fields are server controlled" in block
    assert "COALESCE(last_sequence, 0) + 1" in block
    assert "COALESCE(last_hash" in block


def test_insert_trigger_and_genesis_are_explicit() -> None:
    source = migration_text()
    assert 'GENESIS_HASH = "0" * 64' in source
    assert "CREATE TRIGGER audit_events_hash_chain" in source
    assert "BEFORE INSERT ON public.audit_events" in source
    assert "FOR EACH ROW EXECUTE FUNCTION public.seal_audit_event_v1()" in source


def test_function_privileges_are_least_privilege() -> None:
    source = migration_text()
    assert "REVOKE EXECUTE ON FUNCTION" in source
    assert "FROM PUBLIC" in source
    assert "GRANT EXECUTE ON FUNCTION {payload_signature} TO {RUNTIME_ROLE}" in source
    assert "GRANT EXECUTE ON FUNCTION {hash_signature} TO {RUNTIME_ROLE}" in source
    assert "GRANT EXECUTE ON FUNCTION {seal_signature}" not in source


def test_migration_does_not_claim_worm_or_tamper_proof() -> None:
    source = migration_text().lower()
    assert "not a worm guarantee" in source
    assert "tamper-proof" not in source
