from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_intelligence import (
    REQUIRED_SEED_IDS,
    RepositoryRegistryError,
    load_repository_registry,
    should_index_repository_path,
)

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"


def test_canonical_registry_loads_and_preserves_all_seed_entries() -> None:
    registry = load_repository_registry(REGISTRY_PATH)

    assert registry.schema_version == 1
    assert len(registry.fingerprint) == 64
    assert REQUIRED_SEED_IDS <= {entry["id"] for entry in registry.entries}


def test_required_repository_relationships_are_pinned() -> None:
    registry = load_repository_registry(REGISTRY_PATH)

    council = registry.by_id("imported-council-of-high-intelligence")
    assert council["repository"] == "0xNyk/council-of-high-intelligence"
    assert council["canonical_upstream"] == "0xNyk/council-of-high-intelligence"
    assert council["license"] == {"spdx": "MIT", "status": "VERIFIED"}

    superset = registry.by_id("discovered-apache-superset")
    assert superset["repository"] == "apache/superset"
    assert superset["relation"] == "canonical-analytics-upstream"
    assert superset["license"] == {"spdx": "Apache-2.0", "status": "VERIFIED"}

    patika = registry.by_id("discovered-patika-superset-tr")
    assert patika["canonical_upstream"] == "apache/superset"
    assert patika["relation"] == "localization-vendor-derivative-not-canonical-upstream"


def test_unresolved_archive_identity_is_explicit_not_invented() -> None:
    registry = load_repository_registry(REGISTRY_PATH)

    unresolved = registry.by_id("imported-cl4r1t4s")
    assert unresolved["identity_status"] == "UNRESOLVED"
    assert unresolved["repository"] is None
    assert unresolved["decision"] == "PENDING"


def test_registry_rejects_silent_seed_deletion(tmp_path: Path) -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["entries"] = [
        entry for entry in payload["entries"] if entry["id"] != "imported-impeccable"
    ]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryRegistryError, match="silently dropped"):
        load_repository_registry(path)


def test_registry_rejects_invented_owner_repo_for_unresolved_identity(tmp_path: Path) -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in payload["entries"] if item["id"] == "imported-cl4r1t4s")
    entry["repository"] = "guessed/CL4R1T4S"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryRegistryError, match="rather than inventing owner/repo"):
        load_repository_registry(path)


def test_external_adoption_requires_verified_license(tmp_path: Path) -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in payload["entries"] if item["id"] == "discovered-patika-superset-tr")
    entry["decision"] = "ADOPT"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryRegistryError, match="license verification"):
        load_repository_registry(path)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/repository_intelligence.py", True),
        ("sql/kpi_contract.sql", True),
        (".env", False),
        ("config/.env.production", False),
        ("secrets/jarvis-private-key.pem", False),
        ("keys/id_ed25519", False),
        ("node_modules/package/index.js", False),
        ("vendor/lib/generated.js", False),
        ("dist/app.js", False),
        ("build/model.bin", False),
    ],
)
def test_repository_learning_path_filter(path: str, expected: bool) -> None:
    assert should_index_repository_path(path) is expected
