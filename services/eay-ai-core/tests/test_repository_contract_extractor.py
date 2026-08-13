from __future__ import annotations

import pytest

from app.repository_contract_extractor import RepositoryContractExtractionError, extract_repository_facts


def test_extracts_python_symbols_routes_and_config_names_without_values() -> None:
    source = '''
OPEX_JARVIS_SERVICE_ENABLED = "secret-looking-value"

class JarvisAuthorizer:
    pass

@router.post("/internal/ai/tool-executions/authorize")
def authorize_execution():
    return None
'''
    facts = extract_repository_facts("services/core/app/routes.py", source)

    assert facts.symbols == ("JarvisAuthorizer", "OPEX_JARVIS_SERVICE_ENABLED", "authorize_execution")
    assert "http:POST:/internal/ai/tool-executions/authorize" in facts.contracts
    assert "config:OPEX_JARVIS_SERVICE_ENABLED" in facts.contracts
    assert all("secret-looking-value" not in item for item in facts.contracts)


def test_extracts_sql_schema_contracts() -> None:
    facts = extract_repository_facts(
        "migrations/0011.sql",
        "CREATE TABLE audit_events (id bigint); ALTER TABLE audit_events ADD COLUMN chain_hash text;",
    )

    assert facts.contracts == ("sql:alter-table:audit_events", "sql:create-table:audit_events")


def test_extracts_workflow_structure_without_shell_content() -> None:
    facts = extract_repository_facts(
        ".github/workflows/ci.yml",
        'name: EAY CI\nsteps:\n  - uses: actions/checkout@v4\n  - run: echo "$SUPER_SECRET"\n',
    )

    assert facts.contracts == (
        "workflow:name:EAY CI",
        "workflow:run-step",
        "workflow:uses:actions/checkout@v4",
    )
    assert all("SUPER_SECRET" not in item for item in facts.contracts)


def test_rejects_secret_or_generated_paths() -> None:
    with pytest.raises(RepositoryContractExtractionError, match="excluded"):
        extract_repository_facts("config/.env.production", "TOKEN=secret")


def test_rejects_binary_like_content() -> None:
    with pytest.raises(RepositoryContractExtractionError, match="binary-like"):
        extract_repository_facts("docs/data.txt", "abc\x00def")


def test_rejects_invalid_python_instead_of_guessing_symbols() -> None:
    with pytest.raises(RepositoryContractExtractionError, match="could not be parsed"):
        extract_repository_facts("app/broken.py", "def broken(:")
