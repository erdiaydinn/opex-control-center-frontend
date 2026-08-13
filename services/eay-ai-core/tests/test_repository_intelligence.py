from __future__ import annotations

import json

import pytest

from app.repository_intelligence import (
    REQUIRED_SEED_IDS,
    RepositoryRegistry,
    load_repository_registry,
    load_repository_registry_text,
    should_index_repository_path,
)


def test_registry_loads_cumulative_seed_entries_and_classifies_sources():
    registry = load_repository_registry()
    entries = registry.by_id()

    assert REQUIRED_SEED_IDS <= set(entries)
    assert entries["eay-opex-frontend"].classification == "OWN"
    assert entries["council-high-intelligence"].classification == "IMPORTED"
    assert entries["apache-superset"].classification == "DISCOVERED"
    assert entries["patika-superset-tr"].canonical_upstream == "apache/superset"
    assert len(registry.fingerprint()) == 64


def test_exact_archive_matches_are_promoted_only_to_reviewed_reference_state():
    registry = load_repository_registry()
    cl4r1t4s = registry.by_id("cl4r1t4s")
    computer_lab = registry.by_id("computer-lab-automation")

    assert cl4r1t4s.identity == "elder-plinius/CL4R1T4S"
    assert cl4r1t4s.review.commit == "1a55b8a36d47c86e8d774acef83306d56fb0b302"
    assert cl4r1t4s.review.license == "AGPL-3.0"
    assert cl4r1t4s.decision == "reference"
    assert cl4r1t4s.review.commercial_use == "reference-only-for-proprietary-eay"

    assert computer_lab.identity == "mustafadalga/computer-lab-automation"
    assert computer_lab.review.license == "GPL-3.0"
    assert computer_lab.decision == "reference"


def test_unresolved_identity_is_preserved_and_fail_closed():
    registry = load_repository_registry()
    entry = registry.by_id("impeccable")

    assert entry.identity is None
    assert entry.decision == "pending"
    assert entry.review.commercial_use == "blocked"


def test_registry_rejects_silent_seed_drop(tmp_path):
    source = load_repository_registry().model_dump(mode="json")
    source["repositories"] = [
        entry for entry in source["repositories"] if entry["id"] != "jarvis-master"
    ]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="repository_registry_seed_entries_missing:jarvis-master"):
        load_repository_registry(path)


def test_unresolved_identity_cannot_be_promoted_for_adoption():
    payload = load_repository_registry().model_dump(mode="json")
    for entry in payload["repositories"]:
        if entry["id"] == "impeccable":
            entry["decision"] = "adopt"
            break

    with pytest.raises(ValueError, match="unresolved_repository_identity_must_be_pending"):
        RepositoryRegistry.model_validate(payload)


def test_registry_text_loader_keeps_same_validation_contract():
    registry = load_repository_registry()
    restored = load_repository_registry_text(
        json.dumps(registry.model_dump(mode="json"), ensure_ascii=False)
    )
    assert restored.fingerprint() == registry.fingerprint()


def test_canonical_superset_license_review_is_recorded():
    registry = load_repository_registry()
    superset = registry.by_id("apache-superset")

    assert superset.review.license == "Apache-2.0"
    assert superset.review.commercial_use == "allowed-with-license-obligations"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/repository_intelligence.py", True),
        ("sql/kpi_contract.sql", True),
        ("../escape.py", False),
        ("/absolute/path.py", False),
        (r"C:\\secret\\file.py", False),
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
