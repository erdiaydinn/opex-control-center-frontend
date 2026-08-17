from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_candidate_evidence import (
    build_archive_match_promotion_proposal,
    validate_candidate_evidence,
)
from app.repository_intelligence import RepositoryRegistryError, load_repository_registry


CONFIG_ROOT = Path(__file__).parents[1] / "config"
REGISTRY_PATH = CONFIG_ROOT / "repository_intelligence_registry.json"
CANDIDATE_PATH = CONFIG_ROOT / "repository_intelligence_candidate_evidence.json"


def _registry_and_evidence() -> tuple[object, dict[str, object]]:
    registry = load_repository_registry(REGISTRY_PATH)
    evidence = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    return registry, evidence


def _deep_learning_archive_evidence() -> dict[str, object]:
    return {
        "registry_entry_id": "imported-deep-learning-tutorials",
        "archive": "Deep-Learning-Tutorials-master.zip",
        "archive_sha256": "a" * 64,
        "canonical_repository": "lisa-lab/DeepLearningTutorials",
        "ref": "historical-ref",
        "commit_sha": "b" * 40,
        "tree_sha": "c" * 40,
        "license_spdx": "BSD-3-Clause",
        "match": "EXACT_RECOMPUTED_GIT_TREE",
    }


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


def test_exact_archive_match_only_builds_non_mutating_human_review_proposal() -> None:
    registry, evidence = _registry_and_evidence()
    proposal = build_archive_match_promotion_proposal(
        registry,
        evidence,
        _deep_learning_archive_evidence(),
    )

    assert proposal["canonical_repository"] == "lisa-lab/DeepLearningTutorials"
    assert proposal["archive_match"] == "EXACT_RECOMPUTED_GIT_TREE"
    assert proposal["decision"] == "REFERENCE"
    assert proposal["human_review_required"] is True
    assert proposal["registry_mutation_permitted"] is False
    assert registry.by_id("imported-deep-learning-tutorials")["identity_status"] == "UNRESOLVED"


def test_promotion_rejects_repository_substitution() -> None:
    registry, evidence = _registry_and_evidence()
    archive_evidence = _deep_learning_archive_evidence()
    archive_evidence["canonical_repository"] = "attacker/substitute"

    with pytest.raises(RepositoryRegistryError, match="repository does not match candidate evidence"):
        build_archive_match_promotion_proposal(registry, evidence, archive_evidence)


def test_promotion_rejects_non_exact_archive_match() -> None:
    registry, evidence = _registry_and_evidence()
    archive_evidence = _deep_learning_archive_evidence()
    archive_evidence["match"] = "PATH_SIMILARITY"

    with pytest.raises(RepositoryRegistryError, match="requires exact recomputed Git tree"):
        build_archive_match_promotion_proposal(registry, evidence, archive_evidence)


def test_promotion_rejects_archive_digest_smuggling() -> None:
    registry, evidence = _registry_and_evidence()
    archive_evidence = _deep_learning_archive_evidence()
    archive_evidence["archive_sha256"] = "not-a-sha256"

    with pytest.raises(RepositoryRegistryError, match="archive_sha256 must be an exact lowercase SHA-256"):
        build_archive_match_promotion_proposal(registry, evidence, archive_evidence)


def test_promotion_rejects_license_substitution() -> None:
    registry, evidence = _registry_and_evidence()
    archive_evidence = _deep_learning_archive_evidence()
    archive_evidence["license_spdx"] = "MIT"

    with pytest.raises(RepositoryRegistryError, match="license does not match candidate evidence"):
        build_archive_match_promotion_proposal(registry, evidence, archive_evidence)


def test_promotion_requires_exact_reviewed_field_set() -> None:
    registry, evidence = _registry_and_evidence()
    archive_evidence = _deep_learning_archive_evidence()
    archive_evidence["unreviewed_extra"] = "smuggled"

    with pytest.raises(RepositoryRegistryError, match="exact reviewed field set"):
        build_archive_match_promotion_proposal(registry, evidence, archive_evidence)
