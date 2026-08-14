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
    assert council["last_reviewed_sha"] == "c4d91f07c96e8bc36e3872bbf378ebd4e3f0ac72"
    assert council["license"] == {"spdx": "MIT", "status": "VERIFIED"}
    assert council["decision"] == "WATCH"

    cl4 = registry.by_id("imported-cl4r1t4s")
    assert cl4["repository"] == "elder-plinius/CL4R1T4S"
    assert cl4["canonical_upstream"] == "elder-plinius/CL4R1T4S"
    assert cl4["last_reviewed_sha"] == "1a55b8a36d47c86e8d774acef83306d56fb0b302"
    assert cl4["license"] == {"spdx": "AGPL-3.0", "status": "VERIFIED"}
    assert cl4["decision"] == "REFERENCE"

    computer_lab = registry.by_id("imported-computer-lab-automation")
    assert computer_lab["repository"] == "mustafadalga/computer-lab-automation"
    assert computer_lab["canonical_upstream"] == "mustafadalga/computer-lab-automation"
    assert computer_lab["last_reviewed_sha"] == "0f6fa81448062488f01144c67032764af25ee5fe"
    assert computer_lab["license"] == {"spdx": "GPL-3.0", "status": "VERIFIED"}
    assert computer_lab["decision"] == "REFERENCE"

    superset = registry.by_id("discovered-apache-superset")
    assert superset["repository"] == "apache/superset"
    assert superset["relation"] == "canonical-analytics-upstream"
    assert superset["license"] == {"spdx": "Apache-2.0", "status": "VERIFIED"}

    patika = registry.by_id("discovered-patika-superset-tr")
    assert patika["canonical_upstream"] == "apache/superset"
    assert patika["relation"] == "localization-vendor-derivative-not-canonical-upstream"


def test_recovered_selected_reference_identities_are_exact_and_non_archive_authoritative() -> None:
    registry = load_repository_registry(REGISTRY_PATH)

    llama = registry.by_id("discovered-llama-cpp")
    assert llama["repository"] == "ggml-org/llama.cpp"
    assert llama["last_reviewed_ref"] == "master"
    assert llama["last_reviewed_sha"] == "885c5bbe8e04dc78db25beb911a2715312ad7b54"
    assert llama["license"] == {"spdx": "MIT", "status": "VERIFIED"}
    assert "match pending" in llama["relation"]

    ollama = registry.by_id("discovered-ollama")
    assert ollama["repository"] == "ollama/ollama"
    assert ollama["last_reviewed_ref"] == "main"
    assert ollama["last_reviewed_sha"] == "39df91c9826b3c0c83677f75cd230d8848d287c3"
    assert ollama["license"] == {"spdx": "MIT", "status": "VERIFIED"}
    assert "match pending" in ollama["relation"]

    langgraph = registry.by_id("discovered-langgraph")
    assert langgraph["repository"] == "langchain-ai/langgraph"
    assert langgraph["last_reviewed_ref"] == "main"
    assert langgraph["last_reviewed_sha"] == "644815f9e5bc52ad8f7a5227a456227e9c3e639b"
    assert langgraph["license"] == {"spdx": "MIT", "status": "VERIFIED"}
    assert "match pending" in langgraph["relation"]

    # Public repository identity is verified independently; the supplied ZIPs
    # are still non-authoritative until archive SHA/tree matching succeeds.
    for entry in (llama, ollama, langgraph):
        assert entry["classification"] == "DISCOVERED"
        assert entry["identity_status"] == "VERIFIED"
        assert entry["decision"] == "WATCH"
        assert not entry["relation"].startswith("supplied-archive-to-canonical-upstream")


def test_unresolved_archive_identity_is_explicit_not_invented() -> None:
    registry = load_repository_registry(REGISTRY_PATH)

    unresolved = registry.by_id("imported-deep-learning-tutorials")
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


def test_recovered_selected_reference_cannot_be_silently_dropped(tmp_path: Path) -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["entries"] = [entry for entry in payload["entries"] if entry["id"] != "discovered-llama-cpp"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryRegistryError, match="silently dropped"):
        load_repository_registry(path)


def test_registry_rejects_duplicate_verified_repository_identity(tmp_path: Path) -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    ollama = next(item for item in payload["entries"] if item["id"] == "discovered-ollama")
    duplicate = dict(ollama)
    duplicate["id"] = "discovered-ollama-shadow"
    duplicate["display_name"] = "Ollama shadow"
    duplicate["repository"] = "OLLAMA/OLLAMA"
    payload["entries"].append(duplicate)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryRegistryError, match="cannot be duplicated"):
        load_repository_registry(path)


def test_registry_rejects_invented_owner_repo_for_unresolved_identity(tmp_path: Path) -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(
        item for item in payload["entries"] if item["id"] == "imported-deep-learning-tutorials"
    )
    entry["repository"] = "guessed/Deep-Learning-Tutorials"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryRegistryError, match="rather than inventing owner/repo"):
        load_repository_registry(path)


def test_copyleft_archives_remain_reference_only_for_proprietary_eay() -> None:
    registry = load_repository_registry(REGISTRY_PATH)

    for entry_id, spdx in (
        ("imported-cl4r1t4s", "AGPL-3.0"),
        ("imported-computer-lab-automation", "GPL-3.0"),
    ):
        entry = registry.by_id(entry_id)
        assert entry["license"] == {"spdx": spdx, "status": "VERIFIED"}
        assert entry["decision"] == "REFERENCE"


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
