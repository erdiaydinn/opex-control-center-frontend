from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from .repository_intelligence import RepositoryRegistry, should_index_repository_path
from .repository_provenance import KnowledgeKind, RepositoryFact, make_repository_fact


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
class GitHubTreeEvidence:
    repository: str
    tree_sha: str
    truncated: bool


@dataclass(frozen=True)
class GitHubTreeEntryEvidence:
    path: str
    mode: str
    object_type: str
    object_sha: str


@dataclass(frozen=True)
class GitHubFetchedTextEvidence:
    repository: str
    commit_sha: str
    path: str
    blob_sha: str
    source_text: str


@dataclass(frozen=True)
class VerifiedGitHubTextFile:
    repository: str
    reviewed_ref: str
    commit_sha: str
    path: str
    blob_sha: str
    content_sha256: str
    source_text: str


def _is_sha1(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value.lower())


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    if normalized != path or not should_index_repository_path(normalized):
        raise GitHubRepositoryEvidenceError("github_repository_evidence_path_rejected")
    return normalized


def git_blob_sha1(source_text: str) -> str:
    """Return GitHub/Git blob object identity for UTF-8 text.

    GitHub's current Git data API documents tree/blob object identifiers as SHA-1. EAY also keeps
    a separate SHA-256 content digest for project-memory integrity.
    """
    payload = source_text.encode("utf-8")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()  # noqa: S324 - Git object identity protocol.


def verify_github_text_files(
    *,
    registry: RepositoryRegistry,
    registry_entry_id: str,
    resolved_ref: GitHubResolvedRefEvidence,
    commit: GitHubCommitEvidence,
    tree: GitHubTreeEvidence,
    tree_entries: Iterable[GitHubTreeEntryEvidence],
    files: Iterable[GitHubFetchedTextEvidence],
) -> tuple[VerifiedGitHubTextFile, ...]:
    entry = registry.by_id().get(registry_entry_id)
    if entry is None or entry.identity is None:
        raise GitHubRepositoryEvidenceError("github_repository_registry_identity_unverified")
    if entry.identity != resolved_ref.repository:
        raise GitHubRepositoryEvidenceError("github_repository_registry_identity_mismatch")
    if entry.review.ref is not None and entry.review.ref != resolved_ref.reviewed_ref:
        raise GitHubRepositoryEvidenceError("github_repository_reviewed_ref_mismatch")
    if not _is_sha1(resolved_ref.commit_sha):
        raise GitHubRepositoryEvidenceError("github_repository_resolved_commit_invalid")
    if entry.review.commit is not None and entry.review.commit != resolved_ref.commit_sha:
        raise GitHubRepositoryEvidenceError("github_repository_reviewed_commit_mismatch")

    if commit.repository != resolved_ref.repository or commit.commit_sha != resolved_ref.commit_sha:
        raise GitHubRepositoryEvidenceError("github_repository_commit_binding_mismatch")
    if not _is_sha1(commit.tree_sha):
        raise GitHubRepositoryEvidenceError("github_repository_commit_tree_invalid")
    if tree.repository != resolved_ref.repository or tree.tree_sha != commit.tree_sha:
        raise GitHubRepositoryEvidenceError("github_repository_tree_binding_mismatch")
    if tree.truncated:
        raise GitHubRepositoryEvidenceError("github_repository_tree_truncated")

    accepted_modes = {"100644", "100755"}
    by_path: dict[str, GitHubTreeEntryEvidence] = {}
    for item in tree_entries:
        path = _normalized_path(item.path)
        if path in by_path:
            raise GitHubRepositoryEvidenceError("github_repository_duplicate_tree_path")
        if item.object_type != "blob" or item.mode not in accepted_modes:
            continue
        if not _is_sha1(item.object_sha):
            raise GitHubRepositoryEvidenceError("github_repository_tree_blob_invalid")
        by_path[path] = item

    verified: list[VerifiedGitHubTextFile] = []
    seen: set[str] = set()
    for fetched in files:
        if fetched.repository != resolved_ref.repository or fetched.commit_sha != resolved_ref.commit_sha:
            raise GitHubRepositoryEvidenceError("github_repository_file_binding_mismatch")
        path = _normalized_path(fetched.path)
        if path in seen:
            raise GitHubRepositoryEvidenceError("github_repository_duplicate_fetched_path")
        seen.add(path)
        tree_entry = by_path.get(path)
        if tree_entry is None:
            raise GitHubRepositoryEvidenceError("github_repository_file_absent_from_tree")
        if fetched.blob_sha != tree_entry.object_sha:
            raise GitHubRepositoryEvidenceError("github_repository_blob_tree_mismatch")
        if git_blob_sha1(fetched.source_text) != fetched.blob_sha:
            raise GitHubRepositoryEvidenceError("github_repository_blob_content_mismatch")
        verified.append(
            VerifiedGitHubTextFile(
                repository=fetched.repository,
                reviewed_ref=resolved_ref.reviewed_ref,
                commit_sha=fetched.commit_sha,
                path=path,
                blob_sha=fetched.blob_sha,
                content_sha256=hashlib.sha256(fetched.source_text.encode("utf-8")).hexdigest(),
                source_text=fetched.source_text,
            )
        )

    if not verified:
        raise GitHubRepositoryEvidenceError("github_repository_verified_file_required")
    return tuple(verified)


def make_fact_from_verified_github_file(
    *,
    registry: RepositoryRegistry,
    registry_entry_id: str,
    verified_file: VerifiedGitHubTextFile,
    kind: KnowledgeKind,
    contract: str,
    symbol: str | None = None,
) -> RepositoryFact:
    entry = registry.by_id().get(registry_entry_id)
    if entry is None or entry.identity != verified_file.repository:
        raise GitHubRepositoryEvidenceError("github_repository_fact_registry_mismatch")
    if entry.review.ref is not None and entry.review.ref != verified_file.reviewed_ref:
        raise GitHubRepositoryEvidenceError("github_repository_fact_ref_mismatch")
    if entry.review.commit is not None and entry.review.commit != verified_file.commit_sha:
        raise GitHubRepositoryEvidenceError("github_repository_fact_commit_mismatch")

    fact = make_repository_fact(
        registry=registry,
        repository_id=registry_entry_id,
        ref=verified_file.reviewed_ref,
        commit_sha=verified_file.commit_sha,
        path=verified_file.path,
        kind=kind,
        contract=contract,
        content=verified_file.source_text.encode("utf-8"),
        symbol=symbol,
    )
    if fact.content_sha256 != verified_file.content_sha256:
        raise GitHubRepositoryEvidenceError("github_repository_fact_content_digest_mismatch")
    return fact
