from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_license_boundary import (
    RepositoryLicenseBoundaryError,
    load_repository_license_boundary,
    load_repository_license_boundary_text,
)

EVIDENCE_PATH = (
    Path(__file__).parents[1] / "config" / "repository_license_boundary_evidence.json"
)


def _mutated(**changes: object) -> str:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    payload["records"][0].update(changes)
    return json.dumps(payload)


def test_canonical_mixed_license_evidence_is_reviewable_reference_only() -> None:
    ledger = load_repository_license_boundary(EVIDENCE_PATH)
    record = ledger.records[0]
    assert record.repository == "langfuse/langfuse"
    assert record.decision == "REFERENCE"
    assert record.license_boundary == "MIXED"
    assert record.restricted_paths == ["ee/", "web/src/ee/", "worker/src/ee/"]


def test_mixed_license_repository_cannot_be_promoted_to_adopt() -> None:
    with pytest.raises(RepositoryLicenseBoundaryError, match="cannot_be_adoption_authority"):
        load_repository_license_boundary_text(_mutated(decision="ADOPT"))


def test_mixed_license_repository_requires_restricted_paths() -> None:
    with pytest.raises(RepositoryLicenseBoundaryError, match="restricted_paths_required"):
        load_repository_license_boundary_text(_mutated(restricted_paths=[]))


def test_mixed_license_repository_rejects_invalid_commit_identity() -> None:
    with pytest.raises(RepositoryLicenseBoundaryError, match="invalid_git_identity"):
        load_repository_license_boundary_text(_mutated(commit_sha="deadbeef"))


def test_mixed_license_repository_requires_separate_license_boundary() -> None:
    with pytest.raises(RepositoryLicenseBoundaryError, match="commercial_boundary_missing"):
        load_repository_license_boundary_text(
            _mutated(commercial_use_policy="CORE_ONLY_UNDER_MIT")
        )
