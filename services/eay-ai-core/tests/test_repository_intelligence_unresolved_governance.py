from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_intelligence import RepositoryRegistryError
from app.repository_intelligence_governance import (
    load_governed_repository_registry,
    validate_archive_provenance_governance,
)

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"
PROVENANCE_PATH = Path(__file__).parents[1] / "config" / "repository_archive_provenance.json"


def _write_mutated_registry(tmp_path: Path, entry_id: str, **changes: object) -> Path:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in payload["entries"] if item["id"] == entry_id)
    entry.update(changes)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _provenance_payload() -> dict[str, object]:
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


def _record(payload: dict[str, object], entry_id: str) -> dict[str, object]:
    records = payload["records"]
    assert isinstance(records, list)
    return next(record for record in records if record["registry_entry_id"] == entry_id)


def test_canonical_registry_passes_strict_governance() -> None:
    registry = load_governed_repository_registry(REGISTRY_PATH)
    assert registry.schema_version == 1
    assert registry.unresolved


def test_canonical_archive_provenance_matches_governed_registry() -> None:
    registry = load_governed_repository_registry(REGISTRY_PATH)
    validate_archive_provenance_governance(registry, _provenance_payload())


def test_unresolved_identity_cannot_claim_canonical_upstream(tmp_path: Path) -> None:
    path = _write_mutated_registry(
        tmp_path,
        "imported-deep-learning-tutorials",
        canonical_upstream="guessed/Deep-Learning-Tutorials",
    )
    with pytest.raises(RepositoryRegistryError, match="cannot assert repository identity"):
        load_governed_repository_registry(path)


def test_unresolved_identity_cannot_leave_pending_decision(tmp_path: Path) -> None:
    path = _write_mutated_registry(
        tmp_path,
        "imported-deep-learning-tutorials",
        decision="REFERENCE",
    )
    with pytest.raises(RepositoryRegistryError, match="must remain PENDING"):
        load_governed_repository_registry(path)


def test_unresolved_identity_cannot_claim_verified_license(tmp_path: Path) -> None:
    path = _write_mutated_registry(
        tmp_path,
        "imported-deep-learning-tutorials",
        license={"spdx": "MIT", "status": "VERIFIED"},
    )
    with pytest.raises(RepositoryRegistryError, match="must keep license PENDING"):
        load_governed_repository_registry(path)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("canonical_repository", "attacker/shadow", "repository mismatch"),
        ("commit_sha", "0" * 40, "commit mismatch"),
        ("match", "NAME_SIMILARITY_ONLY", "not promotion-grade"),
        ("archive_sha256", "not-a-sha", "invalid archive_sha256"),
    ],
)
def test_archive_provenance_substitution_fails_closed(
    field: str,
    replacement: object,
    message: str,
) -> None:
    registry = load_governed_repository_registry(REGISTRY_PATH)
    payload = _provenance_payload()
    _record(payload, "imported-council-of-high-intelligence")[field] = replacement
    with pytest.raises(RepositoryRegistryError, match=message):
        validate_archive_provenance_governance(registry, payload)


def test_archive_provenance_license_substitution_fails_closed() -> None:
    registry = load_governed_repository_registry(REGISTRY_PATH)
    payload = _provenance_payload()
    _record(payload, "imported-council-of-high-intelligence")["license"] = {
        "spdx": "Apache-2.0",
        "status": "VERIFIED",
    }
    with pytest.raises(RepositoryRegistryError, match="license mismatch"):
        validate_archive_provenance_governance(registry, payload)


def test_archive_provenance_cannot_promote_unresolved_candidate() -> None:
    registry = load_governed_repository_registry(REGISTRY_PATH)
    payload = _provenance_payload()
    records = payload["records"]
    assert isinstance(records, list)
    records.append(
        {
            "registry_entry_id": "imported-deep-learning-tutorials",
            "archive": "Deep-Learning-Tutorials-master.zip",
            "archive_sha256": "1" * 64,
            "canonical_repository": "lisa-lab/DeepLearningTutorials",
            "ref": "master",
            "commit_sha": "2" * 40,
            "tree_sha": "3" * 40,
            "readme_blob_sha": "4" * 40,
            "license_blob_sha": "5" * 40,
            "match": "EXACT_RECOMPUTED_GIT_TREE",
            "license": {"spdx": "BSD-3-Clause", "status": "VERIFIED"},
            "commercial_use": "REFERENCE_ONLY",
            "decision": "REFERENCE",
        }
    )
    with pytest.raises(RepositoryRegistryError, match="requires verified IMPORTED entry"):
        validate_archive_provenance_governance(registry, payload)
