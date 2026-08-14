from __future__ import annotations

import json

import pytest

from app.repository_intelligence import (
    RepositoryRegistry,
    load_repository_registry,
    should_index_repository_path,
)


def test_registry_loads_seed_entries_and_classifies_sources():
    registry = load_repository_registry()
    entries = registry.by_id()

    assert entries["eay-opex-frontend"].classification == "OWN"
    assert entries["council-high-intelligence"].classification == "IMPORTED"
    assert entries["apache-superset"].classification == "DISCOVERED"
    assert entries["patika-superset-tr"].canonical_upstream == "apache/superset"
    assert len(registry.fingerprint()) == 64


def test_verified_archive_provenance_is_promoted_without_adoption_authority():
    registry = load_repository_registry()
    entries = registry.by_id()

    council = entries["council-high-intelligence"]
    assert council.identity == "0xNyk/council-of-high-intelligence"
    assert council.review.commit == "c4d91f07c96e8bc36e3872bbf378ebd4e3f0ac72"
    assert council.review.license == "MIT"
    assert council.decision == "watch"

    cl4 = entries["cl4r1t4s"]
    assert cl4.identity == "elder-plinius/CL4R1T4S"
    assert cl4.review.commit == "1a55b8a36d47c86e8d774acef83306d56fb0b302"
    assert cl4.review.license == "AGPL-3.0"
    assert cl4.decision == "reference"
    assert cl4.review.commercial_use == "reference-only-proprietary-eay"

    lab = entries["computer-lab-automation"]
    assert lab.identity == "mustafadalga/computer-lab-automation"
    assert lab.review.commit == "0f6fa81448062488f01144c67032764af25ee5fe"
    assert lab.review.license == "GPL-3.0"
    assert lab.decision == "reference"


def test_unresolved_identity_is_preserved_and_fail_closed():
    registry = load_repository_registry()
    entry = registry.by_id()["impeccable"]

    assert entry.identity is None
    assert entry.decision == "pending"
    assert entry.review.commercial_use == "blocked"


def test_registry_rejects_silent_seed_drop(tmp_path):
    source = load_repository_registry().model_dump(mode="json")
    source["repositories"] = [
        entry for entry in source["repositories"] if entry["id"] != "jarvis-archives"
    ]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="repository_registry_seed_entries_missing:jarvis-archives"):
        load_repository_registry(path)


def test_unresolved_identity_cannot_be_promoted_for_adoption():
    payload = load_repository_registry().model_dump(mode="json")
    for entry in payload["repositories"]:
        if entry["id"] == "impeccable":
            entry["decision"] = "adopt"
            break

    with pytest.raises(ValueError, match="unresolved_repository_identity_must_be_pending"):
        RepositoryRegistry.model_validate(payload)


def test_canonical_superset_license_review_is_recorded():
    registry = load_repository_registry()
    superset = registry.by_id()["apache-superset"]

    assert superset.review.license == "Apache-2.0"
    assert superset.review.commercial_use == "allowed-with-license-obligations"


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
def test_repository_learning_path_filter(path: str, expected: bool):
    assert should_index_repository_path(path) is expected
