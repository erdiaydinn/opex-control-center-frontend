from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from app.repository_contract_extractor import RepositoryContractExtractionError, extract_repository_facts
from app.repository_intelligence import RepositoryRegistry
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore, RepositoryMemoryStoreError
from app.repository_review_snapshot import (
    RepositoryFileFact,
    RepositoryReviewSnapshot,
    RepositorySnapshotError,
    create_repository_review_snapshot,
)


class RepositoryReviewIngestionError(RuntimeError):
    pass


MAX_REVIEW_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FetchedRepositoryFileEvidence:
    repository: str
    reviewed_ref: str
    commit_sha: str
    path: str
    blob_sha: str
    source_text: str


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def _content_sha256(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def ingest_fetched_repository_review(
    registry: RepositoryRegistry,
    store: AppendOnlyRepositoryMemoryStore,
    *,
    registry_entry_id: str,
    reviewed_ref: str,
    commit_sha: str,
    reviewed_at: str,
    evidence: Iterable[FetchedRepositoryFileEvidence],
) -> RepositoryReviewSnapshot:
    """Persist one review using already-fetched evidence with exact provenance binding.

    Network access intentionally stays outside this function. The caller must fetch a commit and
    its files read-only, then provide the repository/ref/commit/blob metadata returned by that
    source. This coordinator rejects mixed or substituted provenance before extraction/persistence.
    """
    entry = registry.by_id(registry_entry_id)
    repository = entry.get("repository")
    if entry.get("identity_status") != "VERIFIED" or not repository:
        raise RepositoryReviewIngestionError("unresolved repository identity cannot be ingested")
    if not reviewed_ref.strip():
        raise RepositoryReviewIngestionError("reviewed ref is required")
    if not _is_hex(commit_sha, 40):
        raise RepositoryReviewIngestionError("exact 40-character review commit SHA is required")

    fetched = tuple(evidence)
    if not fetched:
        raise RepositoryReviewIngestionError("at least one fetched file evidence record is required")

    facts: list[RepositoryFileFact] = []
    seen_paths: set[str] = set()
    for item in fetched:
        if item.repository != repository:
            raise RepositoryReviewIngestionError("fetched evidence repository does not match registry identity")
        if item.reviewed_ref != reviewed_ref:
            raise RepositoryReviewIngestionError("fetched evidence ref does not match requested review ref")
        if item.commit_sha.lower() != commit_sha.lower():
            raise RepositoryReviewIngestionError("fetched evidence commit does not match requested review commit")
        if not _is_hex(item.blob_sha, 40):
            raise RepositoryReviewIngestionError(f"invalid fetched blob SHA for {item.path}")

        normalized_path = item.path.replace("\\", "/").strip("/")
        if not normalized_path:
            raise RepositoryReviewIngestionError("fetched evidence path is empty")
        if normalized_path in seen_paths:
            raise RepositoryReviewIngestionError(f"duplicate fetched file path: {normalized_path}")
        seen_paths.add(normalized_path)

        encoded = item.source_text.encode("utf-8")
        if len(encoded) > MAX_REVIEW_FILE_BYTES:
            raise RepositoryReviewIngestionError(f"fetched file exceeds review size limit: {normalized_path}")
        try:
            extracted = extract_repository_facts(normalized_path, item.source_text)
        except RepositoryContractExtractionError as exc:
            raise RepositoryReviewIngestionError(f"repository fact extraction failed for {normalized_path}") from exc

        facts.append(
            RepositoryFileFact(
                path=normalized_path,
                blob_sha=item.blob_sha.lower(),
                symbols=extracted.symbols,
                contracts=extracted.contracts,
                content_sha256=_content_sha256(item.source_text),
            )
        )

    try:
        existing = store.list_snapshots(registry_entry_id)
    except RepositoryMemoryStoreError as exc:
        raise RepositoryReviewIngestionError("existing repository memory failed verification") from exc
    previous = existing[-1].fingerprint if existing else None

    try:
        snapshot = create_repository_review_snapshot(
            registry,
            registry_entry_id=registry_entry_id,
            reviewed_ref=reviewed_ref,
            commit_sha=commit_sha,
            reviewed_at=reviewed_at,
            files=facts,
            previous_snapshot_fingerprint=previous,
        )
        store.append(snapshot)
    except (RepositorySnapshotError, RepositoryMemoryStoreError) as exc:
        raise RepositoryReviewIngestionError("repository review could not be committed") from exc

    return snapshot
