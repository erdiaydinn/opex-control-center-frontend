from __future__ import annotations

from pathlib import Path

import pytest

from app.repository_intelligence import load_repository_registry
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore
from app.repository_review_ingestion import (
    FetchedRepositoryFileEvidence,
    RepositoryReviewIngestionError,
    ingest_fetched_repository_review,
)

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"
COMMIT = "cc35056bc96df40e0b0d565c09c665d74a8e74ea"
BLOB = "46510f0e20165b0a809fbad7866f4efc261da9c1"


def _registry():
    return load_repository_registry(REGISTRY_PATH)


def _evidence(**overrides):
    values = {
        "repository": "apache/superset",
        "reviewed_ref": "master",
        "commit_sha": COMMIT,
        "path": "superset/security/api.py",
        "blob_sha": BLOB,
        "source_text": '@router.get("/api/v1/security/guest_token/")\ndef guest_token():\n    return None\n',
    }
    values.update(overrides)
    return FetchedRepositoryFileEvidence(**values)


def test_ingestion_composes_extraction_snapshot_and_append_only_store(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)

    snapshot = ingest_fetched_repository_review(
        registry,
        store,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha=COMMIT,
        reviewed_at="2026-08-13T00:06:00+03:00",
        evidence=[_evidence()],
    )

    assert snapshot.repository == "apache/superset"
    assert snapshot.commit_sha == COMMIT
    assert snapshot.files[0].blob_sha == BLOB
    assert snapshot.files[0].symbols == ("guest_token",)
    assert "http:GET:/api/v1/security/guest_token/" in snapshot.files[0].contracts
    assert len(snapshot.files[0].content_sha256 or "") == 64
    assert store.list_snapshots("discovered-apache-superset") == (snapshot,)


def test_ingestion_rejects_repository_substitution_before_persisting(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)

    with pytest.raises(RepositoryReviewIngestionError, match="repository does not match"):
        ingest_fetched_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha=COMMIT,
            reviewed_at="2026-08-13T00:06:00+03:00",
            evidence=[_evidence(repository="attacker/superset")],
        )
    assert store.list_snapshots("discovered-apache-superset") == ()


def test_ingestion_rejects_ref_or_commit_substitution(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)

    with pytest.raises(RepositoryReviewIngestionError, match="ref does not match"):
        ingest_fetched_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha=COMMIT,
            reviewed_at="2026-08-13T00:06:00+03:00",
            evidence=[_evidence(reviewed_ref="forged")],
        )

    with pytest.raises(RepositoryReviewIngestionError, match="commit does not match"):
        ingest_fetched_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha=COMMIT,
            reviewed_at="2026-08-13T00:06:00+03:00",
            evidence=[_evidence(commit_sha="1" * 40)],
        )


def test_ingestion_rejects_secret_path_and_raw_value_never_reaches_memory(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)

    with pytest.raises(RepositoryReviewIngestionError, match="extraction failed"):
        ingest_fetched_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha=COMMIT,
            reviewed_at="2026-08-13T00:06:00+03:00",
            evidence=[_evidence(path="config/.env.production", source_text="TOKEN=raw-secret")],
        )
    assert store.list_snapshots("discovered-apache-superset") == ()


def test_ingestion_rejects_duplicate_paths_and_oversized_files(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)

    with pytest.raises(RepositoryReviewIngestionError, match="duplicate fetched file path"):
        ingest_fetched_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha=COMMIT,
            reviewed_at="2026-08-13T00:06:00+03:00",
            evidence=[_evidence(), _evidence()],
        )

    with pytest.raises(RepositoryReviewIngestionError, match="size limit"):
        ingest_fetched_repository_review(
            registry,
            store,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha=COMMIT,
            reviewed_at="2026-08-13T00:06:00+03:00",
            evidence=[_evidence(path="docs/large.txt", source_text="x" * (2 * 1024 * 1024 + 1))],
        )


def test_ingestion_appends_to_verified_current_head(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    first = ingest_fetched_repository_review(
        registry,
        store,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha=COMMIT,
        reviewed_at="2026-08-13T00:06:00+03:00",
        evidence=[_evidence()],
    )
    second_commit = "a0d7ec9fafd7a0c2ea1caac5aeef4759c69f5f2e"
    second = ingest_fetched_repository_review(
        registry,
        store,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha=second_commit,
        reviewed_at="2026-08-13T00:07:00+03:00",
        evidence=[_evidence(commit_sha=second_commit, path="superset/models/core.py")],
    )

    assert second.previous_snapshot_fingerprint == first.fingerprint
    assert [item.fingerprint for item in store.list_snapshots("discovered-apache-superset")] == [
        first.fingerprint,
        second.fingerprint,
    ]
