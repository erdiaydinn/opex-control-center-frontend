from __future__ import annotations

import json

import pytest

from app.historical_repository_registry import (
    HistoricalRepositoryRegistryArchive,
    HistoricalRepositoryRegistryError,
    load_historical_repository_registry_text,
)
from app.repository_intelligence import load_repository_registry


def _v1_text() -> str:
    payload = load_repository_registry().model_dump(mode="json")
    payload["version"] = 1
    keep = {
        "eay-opex-frontend",
        "eay-planai-audit",
        "eay-adaronya",
        "council-high-intelligence",
        "cl4r1t4s",
        "computer-lab-automation",
        "deep-learning-tutorials",
        "impeccable",
        "image-understanding",
        "jarvis-archives",
        "apache-superset",
        "patika-superset-tr",
    }
    payload["repositories"] = [entry for entry in payload["repositories"] if entry["id"] in keep]
    return json.dumps(payload)


def test_v1_history_remains_loadable_after_v2_seed_expansion():
    registry = load_historical_repository_registry_text(_v1_text())
    assert registry.version == 1
    assert "jarvis-main-family" not in registry.by_id()
    assert "jarvis-archives" in registry.by_id()


def test_archive_resolves_exact_registry_fingerprint():
    registry = load_historical_repository_registry_text(_v1_text())
    archive = HistoricalRepositoryRegistryArchive([_v1_text()])
    assert archive.resolve(registry.fingerprint()).fingerprint() == registry.fingerprint()


def test_v1_history_still_rejects_original_seed_loss():
    payload = json.loads(_v1_text())
    payload["repositories"] = [
        entry for entry in payload["repositories"] if entry["id"] != "jarvis-archives"
    ]
    with pytest.raises(HistoricalRepositoryRegistryError, match="historical_registry_seed_missing"):
        load_historical_repository_registry_text(json.dumps(payload))
