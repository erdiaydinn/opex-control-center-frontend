from __future__ import annotations

from pathlib import Path

import pytest

from app.github_repository_evidence import (
    GitHubCommitEvidence,
    GitHubFetchedTextEvidence,
    GitHubRepositoryEvidenceError,
    GitHubResolvedRefEvidence,
    GitHubTreeEntryEvidence,
    build_verified_github_file_evidence,
    git_blob_sha,
    ingest_verified_github_repository_review,
)
from app.repository_intelligence import load_repository_registry
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"
REPOSITORY = "apache/superset"
REF = "master"
COMMIT_SHA = "c" * 40
TREE_SHA = "d" * 40
SOURCE = 'def healthcheck():\n    return "ok"\n'
BLOB_SHA = git_blob_sha(SOURCE)
PATH = "superset/health.py"


def _resolved() -> GitHubResolvedRefEvidence:
    return GitHubResolvedRefEvidence(REPOSITORY, REF, COMMIT_SHA)


def _commit() -> GitHubCommitEvidence:
    return GitHubCommitEvidence(REPOSITORY, COMMIT_SHA, TREE_SHA)


def _tree(blob_sha: str = BLOB_SHA) -> tuple[GitHubTreeEntryEvidence, ...]:
    return (GitHubTreeEntryEvidence(REPOSITORY, TREE_SHA, PATH, "blob", blob_sha),)


def _files(source: str = SOURCE, blob_sha: str = BLOB_SHA) -> tuple[GitHubFetchedTextEvidence, ...]:
    return (GitHubFetchedTextEvidence(REPOSITORY, COMMIT_SHA, PATH, blob_sha, source),)


def test_git_blob_sha_matches_git_object_identity_contract() -> None:
    assert git_blob_sha("test content\n") == "d670460b4b4aece5915caf5c68d12f560a9fe3e4"


def test_builds_evidence_only_when_ref_commit_tree_blob_and_content_match() -> None:
    evidence = build_verified_github_file_evidence(
        resolved_ref=_resolved(), commit=_commit(), tree_entries=_tree(), files=_files()
    )
    assert len(evidence) == 1
    assert evidence[0].repository == REPOSITORY
    assert evidence[0].reviewed_ref == REF
    assert evidence[0].commit_sha == COMMIT_SHA
    assert evidence[0].blob_sha == BLOB_SHA


@pytest.mark.parametrize(
    ("resolved", "commit", "tree", "files", "message"),
    [
        (
            GitHubResolvedRefEvidence(REPOSITORY, REF, "a" * 40),
            _commit(),
            _tree(),
            _files(),
            "resolved ref does not point",
        ),
        (
            _resolved(),
            GitHubCommitEvidence(REPOSITORY, COMMIT_SHA, "e" * 40),
            _tree(),
            _files(),
            "not bound to commit tree",
        ),
        (
            _resolved(),
            _commit(),
            _tree("f" * 40),
            _files(),
            "does not match commit tree",
        ),
        (
            _resolved(),
            _commit(),
            _tree(),
            _files(source='def healthcheck():\n    return "tampered"\n'),
            "does not match Git blob identity",
        ),
    ],
)
def test_rejects_provenance_substitution(resolved, commit, tree, files, message: str) -> None:
    with pytest.raises(GitHubRepositoryEvidenceError, match=message):
        build_verified_github_file_evidence(
            resolved_ref=resolved, commit=commit, tree_entries=tree, files=files
        )


def test_rejects_file_absent_from_commit_tree() -> None:
    file = GitHubFetchedTextEvidence(REPOSITORY, COMMIT_SHA, "other.py", BLOB_SHA, SOURCE)
    with pytest.raises(GitHubRepositoryEvidenceError, match="absent from commit tree"):
        build_verified_github_file_evidence(
            resolved_ref=_resolved(), commit=_commit(), tree_entries=_tree(), files=[file]
        )


def test_verified_github_evidence_composes_into_append_only_project_memory(tmp_path: Path) -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)

    snapshot = ingest_verified_github_repository_review(
        registry,
        store,
        registry_entry_id="discovered-apache-superset",
        reviewed_at="2026-08-13T00:14:00+03:00",
        resolved_ref=_resolved(),
        commit=_commit(),
        tree_entries=_tree(),
        files=_files(),
    )

    assert snapshot.repository == REPOSITORY
    assert snapshot.commit_sha == COMMIT_SHA
    assert snapshot.files[0].blob_sha == BLOB_SHA
    assert snapshot.files[0].symbols == ("healthcheck",)
    assert len(store.list_snapshots("discovered-apache-superset")) == 1


def test_registry_identity_is_authority_over_remote_evidence(tmp_path: Path) -> None:
    registry = load_repository_registry(REGISTRY_PATH)
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    wrong = GitHubResolvedRefEvidence("attacker/superset", REF, COMMIT_SHA)

    with pytest.raises(GitHubRepositoryEvidenceError, match="does not match verified registry target"):
        ingest_verified_github_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_at="2026-08-13T00:14:00+03:00",
            resolved_ref=wrong,
            commit=_commit(),
            tree_entries=_tree(),
            files=_files(),
        )
