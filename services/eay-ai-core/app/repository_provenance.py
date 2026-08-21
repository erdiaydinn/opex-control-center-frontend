from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .repository_intelligence import RepositoryRegistry

KnowledgeKind = Literal[
    "code",
    "sql",
    "api-contract",
    "schema",
    "migration",
    "kpi-rule",
    "ci",
    "documentation",
    "security-policy",
    "architecture-decision",
]

SENSITIVE_PATH_PARTS = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
}
GENERATED_PARTS = {"node_modules", "dist", "build", "vendor", ".venv", "__pycache__"}


class RepositoryCoordinate(BaseModel):
    repository_id: str = Field(min_length=1)
    repository: str = Field(min_length=3)
    canonical_upstream: str | None = None
    ref: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class RepositoryFact(BaseModel):
    coordinate: RepositoryCoordinate
    path: str = Field(min_length=1)
    symbol: str | None = None
    kind: KnowledgeKind
    contract: str = Field(min_length=1, max_length=4000)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    supersedes_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def path_is_safe_for_project_memory(self):
        normalized = PurePosixPath(self.path.replace("\\", "/"))
        lowered = {part.lower() for part in normalized.parts}
        if lowered & SENSITIVE_PATH_PARTS:
            raise ValueError("repository_fact_sensitive_path_blocked")
        if lowered & GENERATED_PARTS:
            raise ValueError("repository_fact_generated_or_vendor_path_blocked")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"supersedes_fingerprint"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RepositorySnapshot(BaseModel):
    registry_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    facts: list[RepositoryFact]

    @model_validator(mode="after")
    def immutable_lineage_is_well_formed(self):
        fingerprints = [fact.fingerprint() for fact in self.facts]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("duplicate_repository_fact")
        known = set(fingerprints)
        for fact in self.facts:
            if fact.supersedes_fingerprint is not None and fact.supersedes_fingerprint not in known:
                raise ValueError("repository_fact_supersedes_unknown_fact")
            if fact.supersedes_fingerprint == fact.fingerprint():
                raise ValueError("repository_fact_cannot_supersede_itself")
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def latest_facts(self) -> list[RepositoryFact]:
        superseded = {fact.supersedes_fingerprint for fact in self.facts if fact.supersedes_fingerprint}
        return [fact for fact in self.facts if fact.fingerprint() not in superseded]


def make_repository_fact(
    *,
    registry: RepositoryRegistry,
    repository_id: str,
    ref: str,
    commit_sha: str,
    path: str,
    kind: KnowledgeKind,
    contract: str,
    content: bytes,
    symbol: str | None = None,
    observed_at: datetime | None = None,
    supersedes_fingerprint: str | None = None,
) -> RepositoryFact:
    entry = registry.by_id().get(repository_id)
    if entry is None:
        raise ValueError("repository_fact_registry_entry_missing")
    if entry.identity is None:
        raise ValueError("repository_fact_unverified_identity_blocked")
    if entry.review.commit is not None and entry.review.commit != commit_sha:
        raise ValueError("repository_fact_commit_not_reviewed")
    if entry.review.ref is not None and entry.review.ref != ref:
        raise ValueError("repository_fact_ref_not_reviewed")

    return RepositoryFact(
        coordinate=RepositoryCoordinate(
            repository_id=entry.id,
            repository=entry.identity,
            canonical_upstream=entry.canonical_upstream,
            ref=ref,
            commit_sha=commit_sha,
        ),
        path=path,
        symbol=symbol,
        kind=kind,
        contract=contract,
        content_sha256=hashlib.sha256(content).hexdigest(),
        observed_at=observed_at or datetime.now(timezone.utc),
        supersedes_fingerprint=supersedes_fingerprint,
    )


def build_repository_snapshot(*, registry: RepositoryRegistry, facts: list[RepositoryFact]) -> RepositorySnapshot:
    valid_ids = set(registry.by_id())
    for fact in facts:
        if fact.coordinate.repository_id not in valid_ids:
            raise ValueError("repository_snapshot_unknown_registry_entry")
        entry = registry.by_id()[fact.coordinate.repository_id]
        if entry.identity != fact.coordinate.repository:
            raise ValueError("repository_snapshot_identity_drift")
        if entry.canonical_upstream != fact.coordinate.canonical_upstream:
            raise ValueError("repository_snapshot_upstream_drift")
    return RepositorySnapshot(
        registry_fingerprint=registry.fingerprint(),
        created_at=datetime.now(timezone.utc),
        facts=facts,
    )
