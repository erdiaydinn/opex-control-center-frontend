from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.repository_archive_inventory_observation import validate_archive_inventory_observations
from app.repository_intelligence import RepositoryRegistryError, load_repository_registry

CONFIG_ROOT = Path(__file__).parents[1] / "config"
REGISTRY_PATH = CONFIG_ROOT / "repository_intelligence_registry.json"
CANDIDATE_PATH = CONFIG_ROOT / "repository_intelligence_candidate_evidence.json"


def _registry_and_payload():
    registry = load_repository_registry(REGISTRY_PATH)
    payload = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    return registry, payload


def test_canonical_archive_inventory_observations_are_non_promoting() -> None:
    registry, payload = _registry_and_payload()
    validated = validate_archive_inventory_observations(registry, payload)

    assert len(validated["candidates"]) >= 7
    for candidate in validated["candidates"]:
        observation = candidate["archive_inventory_observation"]
        assert observation["size_bytes"] > 0
        assert observation["source_trust"] == "NON_CRYPTOGRAPHIC_DIRECTORY_LISTING"
        assert observation["promotion_effect"] == "NONE"
        entry = registry.by_id(candidate["registry_entry_id"])
        assert entry["identity_status"] == "UNRESOLVED"
        assert entry["decision"] == "PENDING"


def test_inventory_observation_cannot_claim_promotion_effect() -> None:
    registry, payload = _registry_and_payload()
    mutated = copy.deepcopy(payload)
    mutated["candidates"][0]["archive_inventory_observation"]["promotion_effect"] = "PROMOTE"

    with pytest.raises(RepositoryRegistryError, match="may not affect promotion"):
        validate_archive_inventory_observations(registry, mutated)


def test_inventory_observation_requires_positive_integer_size() -> None:
    registry, payload = _registry_and_payload()
    mutated = copy.deepcopy(payload)
    mutated["candidates"][0]["archive_inventory_observation"]["size_bytes"] = 0

    with pytest.raises(RepositoryRegistryError, match="positive integer"):
        validate_archive_inventory_observations(registry, mutated)


def test_inventory_observation_rejects_timezone_invention() -> None:
    registry, payload = _registry_and_payload()
    mutated = copy.deepcopy(payload)
    mutated["candidates"][0]["archive_inventory_observation"]["observed_local_mtime"] = (
        "2026-06-02T21:33:00+03:00"
    )

    with pytest.raises(RepositoryRegistryError, match="YYYY-MM-DDTHH:MM:SS"):
        validate_archive_inventory_observations(registry, mutated)


def test_inventory_observation_rejects_cryptographic_overclaim() -> None:
    registry, payload = _registry_and_payload()
    mutated = copy.deepcopy(payload)
    mutated["candidates"][0]["archive_inventory_observation"]["source_trust"] = "CRYPTOGRAPHIC"

    with pytest.raises(RepositoryRegistryError, match="must remain non-cryptographic"):
        validate_archive_inventory_observations(registry, mutated)
