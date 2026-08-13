from __future__ import annotations

import json
from collections.abc import Iterable

from .repository_intelligence import RepositoryRegistry


V1_REQUIRED = {
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


class HistoricalRepositoryRegistryError(ValueError):
    pass


def load_historical_repository_registry_text(source_text: str) -> RepositoryRegistry:
    try:
        payload = json.loads(source_text)
        registry = RepositoryRegistry.model_validate(payload)
    except Exception as exc:
        raise HistoricalRepositoryRegistryError("historical_registry_invalid") from exc

    if registry.version == 1:
        missing = sorted(V1_REQUIRED - set(registry.by_id()))
        if missing:
            raise HistoricalRepositoryRegistryError(
                "historical_registry_seed_missing:" + ",".join(missing)
            )
    else:
        try:
            registry.assert_seed_entries()
        except ValueError as exc:
            raise HistoricalRepositoryRegistryError(str(exc)) from exc
    return registry


class HistoricalRepositoryRegistryArchive:
    def __init__(self, registry_texts: Iterable[str]) -> None:
        self._registries: dict[str, RepositoryRegistry] = {}
        for text in registry_texts:
            registry = load_historical_repository_registry_text(text)
            self._registries.setdefault(registry.fingerprint(), registry)

    def resolve(self, fingerprint: str) -> RepositoryRegistry:
        try:
            return self._registries[fingerprint]
        except KeyError as exc:
            raise HistoricalRepositoryRegistryError("historical_registry_unknown") from exc
