from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.repository_intelligence import load_repository_registry
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore, RepositoryMemoryStoreError
from app.repository_review_snapshot import RepositoryFileFact, create_repository_review_snapshot

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"


def _registry():
    return load_repository_registry(REGISTRY_PATH)


def _snapshot(registry, *, commit_sha: str, reviewed_at: str, previous: str | None = None):
    return create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha=commit_sha,
        reviewed_at=reviewed_at,
        previous_snapshot_fingerprint=previous,
        files=[
            RepositoryFileFact(
                path="superset-frontend/src/dashboard/actions/dashboardState.test.ts",
                blob_sha="46510f0e20165b0a809fbad7866f4efc261da9c1",
                symbols=("saveDashboardRequest",),
                contracts=("dashboard save 403 mapping",),
            )
        ],
    )


def test_store_appends_and_reloads_verified_history(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    first = _snapshot(
        registry,
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:57:00+03:00",
    )
    second = _snapshot(
        registry,
        commit_sha="a0d7ec9fafd7a0c2ea1caac5aeef4759c69f5f2e",
        reviewed_at="2026-08-12T23:58:00+03:00",
        previous=first.fingerprint,
    )

    first_path = store.append(first)
    second_path = store.append(second)

    assert first_path.exists()
    assert second_path.exists()
    loaded = store.list_snapshots("discovered-apache-superset")
    assert [item.fingerprint for item in loaded] == [first.fingerprint, second.fingerprint]


def test_store_rejects_history_fork(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    first = _snapshot(
        registry,
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:57:00+03:00",
    )
    store.append(first)

    fork = _snapshot(
        registry,
        commit_sha="a0d7ec9fafd7a0c2ea1caac5aeef4759c69f5f2e",
        reviewed_at="2026-08-12T23:58:00+03:00",
        previous=None,
    )
    with pytest.raises(RepositoryMemoryStoreError, match="fork or rewrite"):
        store.append(fork)


def test_store_rejects_duplicate_snapshot(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    first = _snapshot(
        registry,
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:57:00+03:00",
    )
    store.append(first)

    with pytest.raises(RepositoryMemoryStoreError):
        store.append(first)


def test_store_detects_snapshot_tampering_on_read(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    first = _snapshot(
        registry,
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:57:00+03:00",
    )
    path = store.append(first)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["reviewed_ref"] = "forged"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RepositoryMemoryStoreError, match="chain verification failed"):
        store.list_snapshots("discovered-apache-superset")


def test_store_detects_index_deletion_or_reorder(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path, registry)
    first = _snapshot(
        registry,
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:57:00+03:00",
    )
    second = _snapshot(
        registry,
        commit_sha="a0d7ec9fafd7a0c2ea1caac5aeef4759c69f5f2e",
        reviewed_at="2026-08-12T23:58:00+03:00",
        previous=first.fingerprint,
    )
    store.append(first)
    store.append(second)

    index_path = tmp_path / "discovered-apache-superset" / "index.jsonl"
    lines = index_path.read_text(encoding="utf-8").splitlines()
    index_path.write_text(lines[1] + "\n" + lines[0] + "\n", encoding="utf-8")

    with pytest.raises(RepositoryMemoryStoreError, match="chain verification failed"):
        store.list_snapshots("discovered-apache-superset")
