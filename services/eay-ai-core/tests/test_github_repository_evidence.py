from __future__ import annotations

import pytest

from app.github_repository_evidence import (
    GitHubCommitEvidence,
    GitHubFetchedTextEvidence,
    GitHubRepositoryEvidenceError,
    GitHubResolvedRefEvidence,
    GitHubTreeEntryEvidence,
    GitHubTreeEvidence,
    git_blob_sha1,
    make_fact_from_verified_github_file,
    verify_github_text_files,
)
from app.repository_intelligence import load_repository_registry


REGISTRY = load_repository_registry()
ENTRY = REGISTRY.by_id("eay-opex-frontend")
SOURCE = "EXAMPLE_POLICY = True\n"
BLOB = git_blob_sha1(SOURCE)
TREE_SHA = "a" * 40


def _inputs():
    resolved = GitHubResolvedRefEvidence(
        repository=ENTRY.identity,
        reviewed_ref=ENTRY.review.ref,
        commit_sha=ENTRY.review.commit,
    )
    commit = GitHubCommitEvidence(
        repository=ENTRY.identity,
        commit_sha=ENTRY.review.commit,
        tree_sha=TREE_SHA,
    )
    tree = GitHubTreeEvidence(repository=ENTRY.identity, tree_sha=TREE_SHA, truncated=False)
    tree_entries = (
        GitHubTreeEntryEvidence(
            path="services/eay-ai-core/app/example_policy.py",
            mode="100644",
            object_type="blob",
            object_sha=BLOB,
        ),
    )
    files = (
        GitHubFetchedTextEvidence(
            repository=ENTRY.identity,
            commit_sha=ENTRY.review.commit,
            path="services/eay-ai-core/app/example_policy.py",
            blob_sha=BLOB,
            source_text=SOURCE,
        ),
    )
    return resolved, commit, tree, tree_entries, files


def test_verified_github_evidence_binds_repo_ref_commit_tree_blob_and_content():
    resolved, commit, tree, tree_entries, files = _inputs()
    verified = verify_github_text_files(
        registry=REGISTRY,
        registry_entry_id=ENTRY.id,
        resolved_ref=resolved,
        commit=commit,
        tree=tree,
        tree_entries=tree_entries,
        files=files,
    )
    assert len(verified) == 1
    assert verified[0].blob_sha == BLOB
    assert len(verified[0].content_sha256) == 64

    fact = make_fact_from_verified_github_file(
        registry=REGISTRY,
        registry_entry_id=ENTRY.id,
        verified_file=verified[0],
        kind="security-policy",
        contract="Example policy is enabled.",
        symbol="EXAMPLE_POLICY",
    )
    assert fact.coordinate.commit_sha == ENTRY.review.commit
    assert fact.content_sha256 == verified[0].content_sha256


def test_truncated_tree_fails_closed():
    resolved, commit, tree, tree_entries, files = _inputs()
    tree = GitHubTreeEvidence(repository=tree.repository, tree_sha=tree.tree_sha, truncated=True)
    with pytest.raises(GitHubRepositoryEvidenceError, match="tree_truncated"):
        verify_github_text_files(
            registry=REGISTRY,
            registry_entry_id=ENTRY.id,
            resolved_ref=resolved,
            commit=commit,
            tree=tree,
            tree_entries=tree_entries,
            files=files,
        )


def test_blob_or_commit_substitution_fails_closed():
    resolved, commit, tree, tree_entries, files = _inputs()
    altered = GitHubFetchedTextEvidence(
        repository=ENTRY.identity,
        commit_sha=ENTRY.review.commit,
        path=files[0].path,
        blob_sha=files[0].blob_sha,
        source_text="EXAMPLE_POLICY = False\n",
    )
    with pytest.raises(GitHubRepositoryEvidenceError, match="blob_content_mismatch"):
        verify_github_text_files(
            registry=REGISTRY,
            registry_entry_id=ENTRY.id,
            resolved_ref=resolved,
            commit=commit,
            tree=tree,
            tree_entries=tree_entries,
            files=(altered,),
        )

    wrong_commit = GitHubCommitEvidence(
        repository=ENTRY.identity,
        commit_sha="b" * 40,
        tree_sha=TREE_SHA,
    )
    with pytest.raises(GitHubRepositoryEvidenceError, match="commit_binding_mismatch"):
        verify_github_text_files(
            registry=REGISTRY,
            registry_entry_id=ENTRY.id,
            resolved_ref=resolved,
            commit=wrong_commit,
            tree=tree,
            tree_entries=tree_entries,
            files=files,
        )


def test_secret_or_generated_path_never_enters_verified_evidence():
    resolved, commit, tree, _, _ = _inputs()
    secret_source = "TOKEN=example\n"
    secret_blob = git_blob_sha1(secret_source)
    with pytest.raises(GitHubRepositoryEvidenceError, match="path_rejected"):
        verify_github_text_files(
            registry=REGISTRY,
            registry_entry_id=ENTRY.id,
            resolved_ref=resolved,
            commit=commit,
            tree=tree,
            tree_entries=(
                GitHubTreeEntryEvidence(
                    path="services/eay-ai-core/.env.production",
                    mode="100644",
                    object_type="blob",
                    object_sha=secret_blob,
                ),
            ),
            files=(
                GitHubFetchedTextEvidence(
                    repository=ENTRY.identity,
                    commit_sha=ENTRY.review.commit,
                    path="services/eay-ai-core/.env.production",
                    blob_sha=secret_blob,
                    source_text=secret_source,
                ),
            ),
        )
