"""Cumulative Repository Intelligence supplement for agent/runtime sources.

The canonical v3 registry remains untouched.  This composer layers reviewed
agent/runtime discoveries on top without dropping any prior entry.  It exists
because external source discovery evolves faster than the owned canonical
registry; consumers that need the latest agent-source provenance should use
``load_repository_registry_with_agent_sources``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .repository_intelligence import (
    DEFAULT_REGISTRY_PATH,
    RepositoryEntry,
    RepositoryRegistry,
    RepositoryRegistryError,
    load_repository_registry_text,
)

AGENT_SOURCE_SUPPLEMENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "repository_intelligence_registry_supplement_v4.json"
)
_REQUIRED_V4_AGENT_SOURCE_IDS = {
    "vercel-agent-browser",
    "e2b-awesome-ai-agents",
}


class AgentSourceRegistrySupplement(BaseModel):
    version: int = Field(ge=4)
    updated_at: str = Field(min_length=10, max_length=10)
    repositories: tuple[RepositoryEntry, ...] = Field(min_length=1)
    required_discovery_domains: tuple[str, ...] = ()

    @model_validator(mode="after")
    def supplement_is_unique(self) -> "AgentSourceRegistrySupplement":
        ids = [item.id for item in self.repositories]
        if len(ids) != len(set(ids)):
            raise ValueError("agent_source_supplement_duplicate_id")
        identities = [item.identity for item in self.repositories if item.identity]
        if len(identities) != len(set(identities)):
            raise ValueError("agent_source_supplement_duplicate_identity")
        missing = sorted(_REQUIRED_V4_AGENT_SOURCE_IDS - set(ids))
        if missing:
            raise ValueError("agent_source_supplement_required_sources_missing:" + ",".join(missing))
        return self


def load_agent_source_supplement(
    path: str | Path = AGENT_SOURCE_SUPPLEMENT_PATH,
) -> AgentSourceRegistrySupplement:
    try:
        return AgentSourceRegistrySupplement.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except ValueError as exc:
        raise RepositoryRegistryError(str(exc)) from exc


def load_repository_registry_with_agent_sources(
    *,
    base_path: str | Path = DEFAULT_REGISTRY_PATH,
    supplement_path: str | Path = AGENT_SOURCE_SUPPLEMENT_PATH,
) -> RepositoryRegistry:
    base = load_repository_registry_text(Path(base_path).read_text(encoding="utf-8"))
    supplement = load_agent_source_supplement(supplement_path)
    if supplement.version <= base.version:
        raise RepositoryRegistryError("agent_source_supplement_must_advance_registry_version")

    existing_ids = set(base.by_id())
    existing_identities = {
        item.identity for item in base.repositories if item.identity is not None
    }
    for item in supplement.repositories:
        if item.id in existing_ids:
            raise RepositoryRegistryError(f"agent_source_supplement_duplicate_base_id:{item.id}")
        if item.identity and item.identity in existing_identities:
            raise RepositoryRegistryError(
                f"agent_source_supplement_duplicate_base_identity:{item.identity}"
            )

    payload = base.model_dump(mode="json")
    payload["version"] = supplement.version
    payload["updated_at"] = supplement.updated_at
    payload["repositories"] = [
        *payload["repositories"],
        *(item.model_dump(mode="json") for item in supplement.repositories),
    ]
    payload["required_discovery_domains"] = list(
        dict.fromkeys(
            [
                *payload["required_discovery_domains"],
                *supplement.required_discovery_domains,
            ]
        )
    )
    merged = RepositoryRegistry.model_validate(payload)
    merged.assert_seed_entries()
    if not _REQUIRED_V4_AGENT_SOURCE_IDS.issubset(set(merged.by_id())):
        raise RepositoryRegistryError("agent_source_registry_merge_lost_required_source")
    return merged
