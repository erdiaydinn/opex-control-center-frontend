from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_intelligence import RepositoryRegistryError, load_repository_registry

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"


def _write_mutated_registry(tmp_path: Path, entry_id: str, **changes: object) -> Path:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in payload["entries"] if item["id"] == entry_id)
    entry.update(changes)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_unresolved_identity_cannot_claim_canonical_upstream(tmp_path: Path) -> None:
    path = _write_mutated_registry(
        tmp_path,
        "imported-deep-learning-tutorials",
        canonical_upstream="guessed/Deep-Learning-Tutorials",
    )
    with pytest.raises(RepositoryRegistryError):
        load_repository_registry(path)


def test_unresolved_identity_cannot_leave_pending_decision(tmp_path: Path) -> None:
    path = _write_mutated_registry(
        tmp_path,
        "imported-deep-learning-tutorials",
        decision="REFERENCE",
    )
    with pytest.raises(RepositoryRegistryError):
        load_repository_registry(path)


def test_unresolved_identity_cannot_claim_verified_license(tmp_path: Path) -> None:
    path = _write_mutated_registry(
        tmp_path,
        "imported-deep-learning-tutorials",
        license={"spdx": "MIT", "status": "VERIFIED"},
    )
    with pytest.raises(RepositoryRegistryError):
        load_repository_registry(path)
