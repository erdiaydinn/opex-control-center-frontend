from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from app.repository_intelligence import RepositoryRegistry, should_index_repository_path


class RepositorySnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class RepositoryFileFact:
    path: str
    blob_sha: str
    symbols: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    content_sha256: str | None = None


@dataclass(frozen=True)
class RepositoryReviewSnapshot:
    schema_version: int
    registry_fingerprint: str
    registry_entry_id: str
    repository: str
    canonical_upstream: str | None
    relation: str
    reviewed_ref: str
    commit_sha: str
    reviewed_at: str
    previous_snapshot_fingerprint: str | None
    files: tuple[RepositoryFileFact, ...]
    fingerprint: str


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def _validate_file_fact(fact: RepositoryFileFact) -> None:
    if not should_index_repository_path(fact.path):
        raise RepositorySnapshotError(f"repository fact path is excluded from learning: {fact.path}")
    if not _is_hex(fact.blob_sha, 40):
        raise RepositorySnapshotError(f"invalid git blob SHA for {fact.path}")
    if fact.content_sha256 is not None and not _is_hex(fact.content_sha256, 64):
        raise RepositorySnapshotError(f"invalid content SHA-256 for {fact.path}")
    if len(set(fact.symbols)) != len(fact.symbols):
        raise RepositorySnapshotError(f"duplicate symbol fact for {fact.path}")
    if len(set(fact.contracts)) != len(fact.contracts):
        raise RepositorySnapshotError(f"duplicate contract fact for {fact.path}")
    if any(not item.strip() for item in (*fact.symbols, *fact.contracts)):
        raise RepositorySnapshotError(f"empty symbol/contract fact for {fact.path}")


def _snapshot_payload(
    *,
    registry_fingerprint: str,
    registry_entry_id: str,
    repository: str,
    canonical_upstream: str | None,
    relation: str,
    reviewed_ref: str,
    commit_sha: str,
    reviewed_at: str,
    previous_snapshot_fingerprint: str | None,
    files: tuple[RepositoryFileFact, ...],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "registry_fingerprint": registry_fingerprint,
        "registry_entry_id": registry_entry_id,
        "repository": repository,
        "canonical_upstream": canonical_upstream,
        "relation": relation,
        "reviewed_ref": reviewed_ref,
        "commit_sha": commit_sha,
        "reviewed_at": reviewed_at,
        "previous_snapshot_fingerprint": previous_snapshot_fingerprint,
        "files": [asdict(fact) for fact in files],
    }


def create_repository_review_snapshot(
    registry: RepositoryRegistry,
    *,
    registry_entry_id: str,
    reviewed_ref: str,
    commit_sha: str,
    reviewed_at: str,
    files: Iterable[RepositoryFileFact],
    previous_snapshot_fingerprint: str | None = None,
) -> RepositoryReviewSnapshot:
    entry = registry.by_id(registry_entry_id)
    if entry["identity_status"] != "VERIFIED" or not entry["repository"]:
        raise RepositorySnapshotError("unresolved repository identity cannot produce a review snapshot")
    if not reviewed_ref.strip():
        raise RepositorySnapshotError("reviewed ref is required")
    if not _is_hex(commit_sha, 40):
        raise RepositorySnapshotError("review snapshot requires an exact 40-character commit SHA")
    if not reviewed_at.strip():
        raise RepositorySnapshotError("reviewed_at is required")
    if previous_snapshot_fingerprint is not None and not _is_hex(previous_snapshot_fingerprint, 64):
        raise RepositorySnapshotError("invalid previous snapshot fingerprint")

    facts = tuple(files)
    if not facts:
        raise RepositorySnapshotError("review snapshot requires at least one provenance-bound file fact")
    paths: set[str] = set()
    for fact in facts:
        _validate_file_fact(fact)
        normalized = fact.path.replace("\\", "/").strip("/")
        if normalized in paths:
            raise RepositorySnapshotError(f"duplicate reviewed file path: {normalized}")
        paths.add(normalized)

    payload = _snapshot_payload(
        registry_fingerprint=registry.fingerprint,
        registry_entry_id=registry_entry_id,
        repository=entry["repository"],
        canonical_upstream=entry["canonical_upstream"],
        relation=entry["relation"],
        reviewed_ref=reviewed_ref,
        commit_sha=commit_sha.lower(),
        reviewed_at=reviewed_at,
        previous_snapshot_fingerprint=previous_snapshot_fingerprint,
        files=facts,
    )
    fingerprint = _sha256(payload)
    return RepositoryReviewSnapshot(
        **payload,
        files=facts,
        fingerprint=fingerprint,
    )


def verify_repository_review_snapshot(
    snapshot: RepositoryReviewSnapshot,
    registry: RepositoryRegistry,
) -> None:
    if snapshot.schema_version != 1:
        raise RepositorySnapshotError("unsupported repository snapshot schema_version")
    if snapshot.registry_fingerprint != registry.fingerprint:
        raise RepositorySnapshotError("repository snapshot is bound to a different registry version")

    entry = registry.by_id(snapshot.registry_entry_id)
    if entry["identity_status"] != "VERIFIED":
        raise RepositorySnapshotError("snapshot registry identity is no longer verified")
    if snapshot.repository != entry["repository"]:
        raise RepositorySnapshotError("snapshot repository identity does not match registry")
    if snapshot.canonical_upstream != entry["canonical_upstream"]:
        raise RepositorySnapshotError("snapshot upstream relation does not match registry")
    if snapshot.relation != entry["relation"]:
        raise RepositorySnapshotError("snapshot repository relation does not match registry")

    for fact in snapshot.files:
        _validate_file_fact(fact)

    payload = _snapshot_payload(
        registry_fingerprint=snapshot.registry_fingerprint,
        registry_entry_id=snapshot.registry_entry_id,
        repository=snapshot.repository,
        canonical_upstream=snapshot.canonical_upstream,
        relation=snapshot.relation,
        reviewed_ref=snapshot.reviewed_ref,
        commit_sha=snapshot.commit_sha,
        reviewed_at=snapshot.reviewed_at,
        previous_snapshot_fingerprint=snapshot.previous_snapshot_fingerprint,
        files=snapshot.files,
    )
    if _sha256(payload) != snapshot.fingerprint:
        raise RepositorySnapshotError("repository snapshot fingerprint mismatch")


def verify_repository_snapshot_chain(
    snapshots: Iterable[RepositoryReviewSnapshot],
    registry: RepositoryRegistry,
) -> None:
    previous: RepositoryReviewSnapshot | None = None
    seen: set[str] = set()
    for snapshot in snapshots:
        verify_repository_review_snapshot(snapshot, registry)
        if snapshot.fingerprint in seen:
            raise RepositorySnapshotError("duplicate repository snapshot fingerprint")
        seen.add(snapshot.fingerprint)

        expected_previous = previous.fingerprint if previous is not None else None
        if snapshot.previous_snapshot_fingerprint != expected_previous:
            raise RepositorySnapshotError("repository snapshot history chain is broken")
        previous = snapshot


def export_repository_review_snapshot(snapshot: RepositoryReviewSnapshot) -> str:
    payload = asdict(snapshot)
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
