from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.repository_intelligence import load_repository_registry
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore, RepositoryMemoryStoreError
from app.repository_provenance import build_repository_snapshot, make_repository_fact


REGISTRY = load_repository_registry()
ENTRY = REGISTRY.by_id("eay-opex-frontend")


def _fact(version: int):
    return make_repository_fact(
        registry=REGISTRY,
        repository_id=ENTRY.id,
        ref=ENTRY.review.ref,
        commit_sha=ENTRY.review.commit,
        path="services/eay-ai-core/app/example_contract.py",
        symbol="EXAMPLE_POLICY",
        kind="security-policy",
        contract=f"Example policy version {version}",
        content=f"EXAMPLE_POLICY={version}\n".encode(),
        observed_at=datetime(2026, 8, 13, 16, version, tzinfo=timezone.utc),
    )


def test_store_round_trip_and_chain(tmp_path):
    store = AppendOnlyRepositoryMemoryStore(tmp_path, REGISTRY)
    first = build_repository_snapshot(
        registry=REGISTRY,
        facts=[_fact(1)],
        created_at=datetime(2026, 8, 13, 16, 1, tzinfo=timezone.utc),
    )
    store.append(first)
    second = build_repository_snapshot(
        registry=REGISTRY,
        facts=[_fact(2)],
        previous_snapshot_fingerprint=first.fingerprint(),
        created_at=datetime(2026, 8, 13, 16, 2, tzinfo=timezone.utc),
    )
    store.append(second)

    loaded = store.list_snapshots()
    assert loaded == (first, second)
    assert loaded[1].previous_snapshot_fingerprint == loaded[0].fingerprint()


def test_store_rejects_non_head_append(tmp_path):
    store = AppendOnlyRepositoryMemoryStore(tmp_path, REGISTRY)
    first = build_repository_snapshot(registry=REGISTRY, facts=[_fact(1)])
    store.append(first)
    second = build_repository_snapshot(registry=REGISTRY, facts=[_fact(2)])

    with pytest.raises(RepositoryMemoryStoreError, match="fork_history"):
        store.append(second)


def test_store_rejects_different_registry_revision(tmp_path):
    store = AppendOnlyRepositoryMemoryStore(tmp_path, REGISTRY)
    snapshot = build_repository_snapshot(registry=REGISTRY, facts=[_fact(1)])
    snapshot.registry_fingerprint = "f" * 64

    with pytest.raises(RepositoryMemoryStoreError, match="snapshot_rejected"):
        store.append(snapshot)
