from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RegistryClass = Literal["OWN", "IMPORTED", "DISCOVERED"]
Decision = Literal[
    "canonical",
    "adopt",
    "watch",
    "reference",
    "localization-reference",
    "reject",
    "pending",
]

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "repository_intelligence_registry.json"
EXCLUDED_PATH_PARTS = {
    ".git", ".venv", "venv", "node_modules", "vendor", "dist", "build",
    "__pycache__", ".next", ".turbo", ".vite",
}
EXCLUDED_FILENAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "credentials.json", "secrets.json",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


class RepositoryRegistryError(ValueError):
    pass


class RepositoryReview(BaseModel):
    ref: str | None = None
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    license: str = Field(min_length=1)
    commercial_use: str = Field(min_length=1)


class RepositoryEntry(BaseModel):
    id: str = Field(min_length=1)
    classification: RegistryClass
    identity: str | None = None
    source_artifact: str | None = None
    canonical_upstream: str | None = None
    decision: Decision
    capabilities: list[str] = Field(default_factory=list)
    review: RepositoryReview

    @model_validator(mode="after")
    def unresolved_identity_is_fail_closed(self):
        if self.identity is None:
            if self.decision != "pending":
                raise ValueError("unresolved_repository_identity_must_be_pending")
            if self.review.commercial_use != "blocked":
                raise ValueError("unresolved_repository_identity_must_block_commercial_use")
        if self.classification == "OWN" and self.identity is None:
            raise ValueError("owned_repository_identity_required")
        if self.canonical_upstream and self.identity is None:
            raise ValueError("canonical_upstream_requires_verified_identity")
        return self


class CanonicalSource(BaseModel):
    repository: str = Field(min_length=1)
    path: str = Field(min_length=1)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")


class RegistryPolicy(BaseModel):
    allowed_classes: list[RegistryClass]
    allowed_decisions: list[Decision]
    never_silently_drop: bool
    unknown_identity_must_remain_pending: bool
    external_code_requires_license_review: bool
    prohibit_risky_auto_merge: bool
    prohibit_unapproved_production_weight_changes: bool


class RepositoryRegistry(BaseModel):
    version: int = Field(ge=1)
    updated_at: str = Field(min_length=10, max_length=10)
    canonical_source: CanonicalSource
    policy: RegistryPolicy
    repositories: list[RepositoryEntry]
    required_discovery_domains: list[str]

    @model_validator(mode="after")
    def registry_invariants(self):
        ids = [entry.id for entry in self.repositories]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_repository_registry_id")
        identities = [entry.identity for entry in self.repositories if entry.identity]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate_verified_repository_identity")
        if not self.policy.never_silently_drop:
            raise ValueError("repository_registry_must_be_cumulative")
        if not self.policy.unknown_identity_must_remain_pending:
            raise ValueError("unresolved_repository_policy_must_fail_closed")
        return self

    def by_id(self) -> dict[str, RepositoryEntry]:
        return {entry.id: entry for entry in self.repositories}

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def assert_seed_entries(self) -> None:
        required = {
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
        missing = sorted(required - set(self.by_id()))
        if missing:
            raise ValueError("repository_registry_seed_entries_missing:" + ",".join(missing))

    def assert_external_license_gate(self) -> None:
        for entry in self.repositories:
            if entry.classification == "OWN" or entry.decision in {
                "watch", "reference", "localization-reference", "reject", "pending"
            }:
                continue
            if entry.review.license in {"pending-review", "unresolved"} or entry.review.commercial_use.startswith("blocked"):
                raise ValueError(f"repository_license_gate_blocked:{entry.id}")


def load_repository_registry_text(source_text: str) -> RepositoryRegistry:
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise RepositoryRegistryError("repository registry is not valid JSON") from exc
    try:
        registry = RepositoryRegistry.model_validate(payload)
        registry.assert_seed_entries()
        return registry
    except ValueError as exc:
        raise RepositoryRegistryError(str(exc)) from exc


def load_repository_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> RepositoryRegistry:
    return load_repository_registry_text(Path(path).read_text(encoding="utf-8"))


def should_index_repository_path(path: str) -> bool:
    """Reject secrets and generated/vendor noise before repository learning."""
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    parts = normalized.split("/")
    lowered = {part.lower() for part in parts}
    if lowered & EXCLUDED_PATH_PARTS:
        return False
    filename = parts[-1].lower()
    if filename in EXCLUDED_FILENAMES or filename.startswith(".env."):
        return False
    if filename.endswith(SECRET_SUFFIXES):
        return False
    if "private" in filename and "key" in filename:
        return False
    return True
