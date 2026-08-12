from __future__ import annotations

import json

import pytest

from app.repository_intelligence import RepositoryRegistry, load_repository_registry


def test_registry_loads_seed_entries_and_classifies_sources():
    registry = load_repository_registry()
    entries = registry.by_id()

    assert entries["eay-opex-frontend"].classification == "OWN"
    assert entries["council-high-intelligence"].classification == "IMPORTED"
    assert entries["apache-superset"].classification == "DISCOVERED"
    assert entries["patika-superset-tr"].canonical_upstream == "apache/superset"
    assert len(registry.fingerprint()) == 64


def test_unresolved_identity_is_preserved_and_fail_closed():
    registry = load_repository_registry()
    entry = registry.by_id()["cl4r1t4s"]

    assert entry.identity is None
    assert entry.decision == "pending"
    assert entry.review.commercial_use == "blocked"


def test_registry_rejects_silent_seed_drop(tmp_path):
    source = json.loads(
        (tmp_path.parent / "does-not-exist").read_text(encoding="utf-8")
    ) if False else load_repository_registry().model_dump(mode="json")
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
