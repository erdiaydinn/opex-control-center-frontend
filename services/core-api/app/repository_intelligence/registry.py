"""Master 40 version-controlled Repository Intelligence registry authority."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Classification = Literal["OWN", "IMPORTED", "DISCOVERED"]
IdentityStatus = Literal["VERIFIED", "UNRESOLVED"]
LicenseStatus = Literal[
    "OWNED",
    "APPROVED_COMMERCIAL",
    "REFERENCE_ONLY_RESTRICTIVE",
    "PENDING_REVIEW",
    "BLOCKED_UNRESOLVED",
]
Decision = Literal["OWN", "ADOPT", "WATCH", "REFERENCE", "PENDING", "REJECT"]
SecurityRelevance = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_CLASSIFICATIONS = frozenset({"OWN", "IMPORTED", "DISCOVERED"})
_IDENTITY_STATUSES = frozenset({"VERIFIED", "UNRESOLVED"})
_LICENSE_STATUSES = frozenset(
    {
        "OWNED",
        "APPROVED_COMMERCIAL",
        "REFERENCE_ONLY_RESTRICTIVE",
        "PENDING_REVIEW",
        "BLOCKED_UNRESOLVED",
    }
)
_DECISIONS = frozenset({"OWN", "ADOPT", "WATCH", "REFERENCE", "PENDING", "REJECT"})
_SECURITY = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
_CODE_SOURCE_LICENSES = frozenset({"OWNED", "APPROVED_COMMERCIAL"})
_CODE_SOURCE_DECISIONS = frozenset({"OWN", "ADOPT"})
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

REQUIRED_SEED_IDS = frozenset(
    {
        "own:opex-control-center-frontend",
        "own:planai-audit",
        "own:adaronya",
        "imported:council-of-high-intelligence",
        "imported:cl4r1t4s",
        "imported:computer-lab-automation",
        "imported:deep-learning-tutorials",
        "imported:impeccable",
        "imported:image-understanding",
        "imported:jarvis-archives",
        "discovered:superset",
        "discovered:superset-tr",
        "discovered:local-llm-serving-set",
        "discovered:agent-orchestration-set",
        "discovered:rag-retrieval-set",
        "discovered:evaluation-set",
        "discovered:observability-set",
        "discovered:vision-document-set",
        "discovered:model-registry-lifecycle-set",
        "discovered:workflow-automation-set",
        "discovered:security-guardrails-set",
        "discovered:fine-tuning-set",
        "discovered:data-catalog-semantic-set",
        "discovered:jarvis-evolution-set",
    }
)


@dataclass(frozen=True)
class RepositoryEntry:
    registry_id: str
    classification: Classification
    repository: str | None
    identity_status: IdentityStatus
    canonical_upstream: str | None
    relation: str
    license_status: LicenseStatus
    decision: Decision
    security_relevance: SecurityRelevance
    source_locator: str | None = None
    archive_name: str | None = None

    @property
    def analysis_permitted(self) -> bool:
        return (
            self.identity_status == "VERIFIED"
            and self.license_status != "BLOCKED_UNRESOLVED"
            and self.decision != "REJECT"
        )

    @property
    def usable_as_code_source(self) -> bool:
        return (
            self.identity_status == "VERIFIED"
            and self.license_status in _CODE_SOURCE_LICENSES
            and self.decision in _CODE_SOURCE_DECISIONS
        )


def _enum(value: object, *, field: str, allowed: frozenset[str]) -> str:
    normalized = str(value).strip()
    if normalized not in allowed:
        raise ValueError(f"unsupported repository registry {field}: {normalized}")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _validate_entry(entry: RepositoryEntry) -> None:
    if not entry.registry_id.strip() or not entry.relation.strip():
        raise ValueError("repository registry identity/relation cannot be empty")

    if entry.identity_status == "VERIFIED":
        if not entry.repository or not _REPOSITORY.fullmatch(entry.repository):
            raise ValueError(f"verified entry requires owner/repo identity: {entry.registry_id}")
    else:
        if entry.repository is not None or entry.canonical_upstream is not None:
            raise ValueError(
                f"unresolved entry cannot guess repository identity: {entry.registry_id}"
            )
        if not entry.source_locator:
            raise ValueError(
                f"unresolved entry requires an explicit source locator: {entry.registry_id}"
            )
        if entry.license_status != "BLOCKED_UNRESOLVED" or entry.decision != "PENDING":
            raise ValueError(f"unresolved entry must remain blocked/pending: {entry.registry_id}")

    if entry.canonical_upstream and not _REPOSITORY.fullmatch(entry.canonical_upstream):
        raise ValueError(f"canonical upstream is not owner/repo: {entry.registry_id}")

    if entry.classification == "OWN" and (
        entry.identity_status != "VERIFIED"
        or entry.relation != "OWN"
        or entry.license_status != "OWNED"
        or entry.decision != "OWN"
        or entry.canonical_upstream is not None
    ):
        raise ValueError(f"OWN source contract is inconsistent: {entry.registry_id}")

    if entry.decision == "ADOPT" and entry.license_status not in _CODE_SOURCE_LICENSES:
        raise ValueError(f"ADOPT requires commercial code-source authority: {entry.registry_id}")
    if entry.license_status == "REFERENCE_ONLY_RESTRICTIVE" and entry.decision == "ADOPT":
        raise ValueError(f"restrictive source cannot be ADOPT: {entry.registry_id}")


def load_registry(path: Path) -> tuple[RepositoryEntry, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 2:
        raise ValueError("unsupported repository registry schema")

    entries: list[RepositoryEntry] = []
    seen: set[str] = set()
    for item in raw.get("entries", []):
        registry_id = str(item.get("registry_id", "")).strip()
        if not registry_id or registry_id in seen:
            raise ValueError("duplicate or empty registry id")
        seen.add(registry_id)

        entry = RepositoryEntry(
            registry_id=registry_id,
            classification=_enum(
                item.get("classification"), field="classification", allowed=_CLASSIFICATIONS
            ),  # type: ignore[arg-type]
            repository=_optional_text(item.get("repository")),
            identity_status=_enum(
                item.get("identity_status"), field="identity_status", allowed=_IDENTITY_STATUSES
            ),  # type: ignore[arg-type]
            canonical_upstream=_optional_text(item.get("canonical_upstream")),
            relation=str(item.get("relation", "")).strip(),
            license_status=_enum(
                item.get("license_status"), field="license_status", allowed=_LICENSE_STATUSES
            ),  # type: ignore[arg-type]
            decision=_enum(
                item.get("decision"), field="decision", allowed=_DECISIONS
            ),  # type: ignore[arg-type]
            security_relevance=_enum(
                item.get("security_relevance"), field="security_relevance", allowed=_SECURITY
            ),  # type: ignore[arg-type]
            source_locator=_optional_text(item.get("source_locator")),
            archive_name=_optional_text(item.get("archive_name")),
        )
        _validate_entry(entry)
        entries.append(entry)

    assert_registry_preserves_required_seeds(tuple(entries))
    return tuple(entries)


def assert_registry_preserves_required_seeds(entries: tuple[RepositoryEntry, ...]) -> None:
    current = {item.registry_id for item in entries}
    missing = sorted(REQUIRED_SEED_IDS - current)
    if missing:
        raise ValueError(
            "repository registry silently dropped required seeds: " + ",".join(missing)
        )
