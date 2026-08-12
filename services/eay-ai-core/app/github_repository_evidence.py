from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from app.repository_review_ingestion import FetchedRepositoryFileEvidence


class GitHubRepositoryEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class GitHubResolvedRefEvidence:
    repository: str
    reviewed_ref: str
    commit_sha: str


@dataclass(frozen=True)
class GitHubCommitEvidence:
    repository: str
    commit_sha: str
    tree_sha: str


@dataclass(frozen=True)
class GitHubTreeEntryEvidence:
    repository: str
    tree_sha: str
    path: str
    object_type: str
    object_sha: str


@dataclass(frozen=True)
class GitHubFetchedTextEvidence:
    repository: str
    commit_sha: str
    path: str
    blob_sha: str
    source_text: str


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def git_blob_sha(source_text: str) -> str:
    payload = source_text.encode("utf-8")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()  # noqa: S324 - Git object identity uses SHA-1 by protocol.


def build_verified_github_file_evidence(
    *,
    resolved_ref: GitHubResolvedRefEvidence,
    commit: GitHubCommitEvidence,
    tree_entries: Iterable[GitHubTreeEntryEvidence],
    files: Iterable[GitHubFetchedTextEvidence],
) -> tuple[FetchedRepositoryFileEvidence, ...]:
    """Validate already-fetched GitHub ref -> commit -> tree -> blob evidence.

    This function performs no network access and accepts no credentials. The caller is responsible
    for fetching immutable GitHub API objects. We only accept evidence when every relationship is
    internally consistent and the fetched UTF-8 text hashes to the exact Git blob SHA.
    """
    repository = resolved_ref.repository
    reviewed_ref = resolved_ref.reviewed_ref.strip()
    commit_sha = resolved_ref.commit_sha.lower()
    if not repository or repository.count("/") != 1:
        raise GitHubRepositoryEvidenceError("exact owner/repo identity is required")
    if not reviewed_ref:
        raise GitHubRepositoryEvidenceError("reviewed ref is required")
    if not _is_hex(commit_sha, 40):
        raise GitHubRepositoryEvidenceError("resolved ref requires an exact 40-character commit SHA")

    if commit.repository != repository:
        raise GitHubRepositoryEvidenceError("commit repository does not match resolved ref")
    if commit.commit_sha.lower() != commit_sha:
        raise GitHubRepositoryEvidenceError("resolved ref does not point to supplied commit")
    if not _is_hex(commit.tree_sha, 40):
        raise GitHubRepositoryEvidenceError("commit tree SHA is invalid")
    tree_sha = commit.tree_sha.lower()

    tree_by_path: dict[str, GitHubTreeEntryEvidence] = {}
    for entry in tree_entries:
        if entry.repository != repository:
            raise GitHubRepositoryEvidenceError("tree entry repository substitution detected")
        if entry.tree_sha.lower() != tree_sha:
            raise GitHubRepositoryEvidenceError("tree entry is not bound to commit tree")
        normalized = entry.path.replace("\\", "/").strip("/")
        if not normalized:
            raise GitHubRepositoryEvidenceError("tree entry path is empty")
        if normalized in tree_by_path:
            raise GitHubRepositoryEvidenceError(f"duplicate tree path: {normalized}")
        if entry.object_type != "blob":
            continue
        if not _is_hex(entry.object_sha, 40):
            raise GitHubRepositoryEvidenceError(f"invalid tree blob SHA for {normalized}")
        tree_by_path[normalized] = entry

    verified: list[FetchedRepositoryFileEvidence] = []
    seen_paths: set[str] = set()
    for item in files:
        if item.repository != repository:
            raise GitHubRepositoryEvidenceError("fetched file repository substitution detected")
        if item.commit_sha.lower() != commit_sha:
            raise GitHubRepositoryEvidenceError("fetched file commit substitution detected")
        normalized = item.path.replace("\\", "/").strip("/")
        if not normalized:
            raise GitHubRepositoryEvidenceError("fetched file path is empty")
        if normalized in seen_paths:
            raise GitHubRepositoryEvidenceError(f"duplicate fetched file path: {normalized}")
        seen_paths.add(normalized)

        tree_entry = tree_by_path.get(normalized)
        if tree_entry is None:
            raise GitHubRepositoryEvidenceError(f"fetched file is absent from commit tree: {normalized}")
        supplied_blob_sha = item.blob_sha.lower()
        if supplied_blob_sha != tree_entry.object_sha.lower():
            raise GitHubRepositoryEvidenceError(f"fetched blob SHA does not match commit tree: {normalized}")
        calculated_blob_sha = git_blob_sha(item.source_text)
        if calculated_blob_sha != supplied_blob_sha:
            raise GitHubRepositoryEvidenceError(f"fetched source does not match Git blob identity: {normalized}")

        verified.append(
            FetchedRepositoryFileEvidence(
                repository=repository,
                reviewed_ref=reviewed_ref,
                commit_sha=commit_sha,
                path=normalized,
                blob_sha=supplied_blob_sha,
                source_text=item.source_text,
            )
        )

    if not verified:
        raise GitHubRepositoryEvidenceError("at least one verified GitHub file is required")
    return tuple(verified)
