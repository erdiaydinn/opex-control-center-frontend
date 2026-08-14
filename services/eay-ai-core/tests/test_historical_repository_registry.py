from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.historical_repository_registry import HistoricalRepositoryRegistryError, load_registry_for_historical_snapshot
from app.repository_intelligence import load_repository_registry
from app.repository_review_snapshot import RepositoryFileFact, create_repository_review_snapshot

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"


def _snapshot(registry):
    return create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="c" * 40,
        reviewed_at="2026-08-13T00:14:00+03:00",
        files=[RepositoryFileFact(path="README.md", blob_sha="d" * 40)],
    )


def test_historical_registry_revalidates_snapshot_without_current_registry_dependency() -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    snapshot = _snapshot(registry)
    source_text = REGISTRY_PATH.read_text(encoding="utf-8")

    historical = load_registry_for_historical_snapshot(source_text, snapshot)

    assert historical.fingerprint == snapshot.registry_fingerprint
    assert historical.by_id("discovered-apache-superset")["repository"] == "apache/superset"


def test_historical_registry_refuses_newer_or_modified_registry_revision() -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    snapshot = _snapshot(registry)
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["updated_at"] = "2026-08-13T00:15:00+03:00"
    changed = json.dumps(payload)

    with pytest.raises(HistoricalRepositoryRegistryError, match="fingerprint does not match"):
        load_registry_for_historical_snapshot(changed, snapshot)


def test_historical_registry_does_not_bypass_seed_or_identity_validation() -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    snapshot = _snapshot(registry)
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["entries"] = [entry for entry in payload["entries"] if entry["id"] != "imported-impeccable"]

    with pytest.raises(HistoricalRepositoryRegistryError, match="historical repository registry is invalid"):
        load_registry_for_historical_snapshot(json.dumps(payload), snapshot)
