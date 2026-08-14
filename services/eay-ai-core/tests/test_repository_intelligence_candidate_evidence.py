from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_candidate_evidence import validate_candidate_evidence
from app.repository_intelligence import RepositoryRegistryError, load_repository_registry


CONFIG_ROOT = Path(__file__).parents[1] / "config"
REGISTRY_PATH = CONFIG_ROOT / "repository_intelligence_registry.json"
CANDIDATE_PATH = CONFIG_ROOT / "repository_intelligence_candidate_evidence.json"


def _registry_and_evidence() -> tuple[object, dict[str, object]]:
    registry = load_repository_registry(REGISTRY_PATH)
    evidence = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    return registry, evidence


def test_canonical_candidate_evidence_passes_fail_closed_validator() -> None:
    registry, evidence = _registry_and_evidence()
    validated = validate_candidate_evidence(registry, evidence)
    assert validated["schema_version"] == 1
    assert validated["candidates"]


def test_candidate_evidence_never_promotes_unresolved_registry_entries() -> None:
    registry, evidence = _registry_and_evidence()
    validate_candidate_evidence(registry, evidence)

    entries = registry.by_id()
    for candidate in evidence["candidates"]:
        entry = entries[candidate["registry_entry_id"]]
        assert entry["identity_status"] == "UNRESOLVED"
        assert entry["repository"] is None
        assert entry["canonical_upstream"] is None
        assert entry["decision"] == "PENDING"
        assert entry["license"] == {"spdx": None, "status": "PENDING"}
        assert candidate["promotion_status"].startswith("BLOCKED_")


def test_candidate_cannot_claim_verified_archive_match() -> None:
    registry, evidence = _registry_and_evidence()
    evidence["candidates"][0]["archive_match_status"] = "VERIFIED"
    with pytest.raises(RepositoryRegistryError, match="may not claim archive verification"):
        validate_candidate_evidence(registry, evidence)


def test_candidate_cannot_target_verified_registry_entry() -> None:
    registry, evidence = _registry_and_evidence()
    evidence["candidates"][0]["registry_entry_id"] = "imported-council-of-high-intelligence"
    evidence["candidates"][0]["archive"] = "council-of-high-intelligence-main.zip"
    with pytest.raises(RepositoryRegistryError, match="cannot target resolved registry entry"):
        validate_candidate_evidence(registry, evidence)


def test_candidate_archive_must_match_registry_source_locator() -> None:
    registry, evidence = _registry_and_evidence()
    evidence["candidates"][0]["archive"] = "different.zip"
    with pytest.raises(RepositoryRegistryError, match="archive does not match registry source"):
        validate_candidate_evidence(registry, evidence)


def test_candidate_repository_requires_complete_git_evidence() -> None:
    registry, evidence = _registry_and_evidence()
    evidence["candidates"][0]["candidate_tree_sha"] = None
    with pytest.raises(RepositoryRegistryError, match="requires branch/head/tree evidence"):
        validate_candidate_evidence(registry, evidence)


def test_missing_candidate_cannot_smuggle_repository_metadata() -> None:
    registry, evidence = _registry_and_evidence()
    missing = next(
        candidate
        for candidate in evidence["candidates"]
        if candidate["candidate_repository"] is None
    )
    missing["candidate_license_spdx"] = "MIT"
    with pytest.raises(RepositoryRegistryError, match="identity fields require candidate_repository"):
        validate_candidate_evidence(registry, evidence)


def test_duplicate_candidate_registry_entry_is_rejected() -> None:
    registry, evidence = _registry_and_evidence()
    evidence["candidates"].append(dict(evidence["candidates"][0]))
    with pytest.raises(RepositoryRegistryError, match="duplicate candidate evidence entry"):
        validate_candidate_evidence(registry, evidence)
