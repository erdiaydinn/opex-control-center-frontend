from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.repository_intelligence import load_repository_registry
from app.repository_review_snapshot import (
    RepositoryFileFact,
    RepositorySnapshotError,
    create_repository_review_snapshot,
    export_repository_review_snapshot,
    verify_repository_review_snapshot,
    verify_repository_snapshot_chain,
)

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"


def _registry():
    return load_repository_registry(REGISTRY_PATH)


def _fact(path: str = "superset-frontend/src/dashboard/actions/dashboardState.test.ts") -> RepositoryFileFact:
    return RepositoryFileFact(
        path=path,
        blob_sha="46510f0e20165b0a809fbad7866f4efc261da9c1",
        symbols=("saveDashboardRequest",),
        contracts=("non-JSON 403 uses generic dashboard save error",),
    )


def test_snapshot_binds_registry_repo_ref_commit_file_symbol_and_contract() -> None:
    registry = _registry()
    snapshot = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:55:00+03:00",
        files=[_fact()],
    )

    verify_repository_review_snapshot(snapshot, registry)
    assert snapshot.repository == "apache/superset"
    assert snapshot.canonical_upstream == "apache/superset"
    assert snapshot.commit_sha == "cc35056bc96df40e0b0d565c09c665d74a8e74ea"
    assert snapshot.files[0].symbols == ("saveDashboardRequest",)
    assert len(snapshot.registry_fingerprint) == 64
    assert len(snapshot.fingerprint) == 64


def test_snapshot_history_is_hash_chained_without_replacing_old_truth() -> None:
    registry = _registry()
    first = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:55:00+03:00",
        files=[_fact()],
    )
    second = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="a0d7ec9fafd7a0c2ea1caac5aeef4759c69f5f2e",
        reviewed_at="2026-08-12T23:56:00+03:00",
        previous_snapshot_fingerprint=first.fingerprint,
        files=[
            RepositoryFileFact(
                path="superset-frontend/packages/superset-ui-core/test/query/getClientErrorObject.test.ts",
                blob_sha="70cc26ba1108f32af4e82b7e74237bfd7871ab19",
                symbols=("getErrorText",),
                contracts=("403 error text maps by response body shape",),
            )
        ],
    )

    verify_repository_snapshot_chain([first, second], registry)
    assert first.commit_sha != second.commit_sha
    assert first.fingerprint != second.fingerprint


def test_chain_rejects_history_rewrite_or_reordering() -> None:
    registry = _registry()
    first = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:55:00+03:00",
        files=[_fact()],
    )
    second = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="a0d7ec9fafd7a0c2ea1caac5aeef4759c69f5f2e",
        reviewed_at="2026-08-12T23:56:00+03:00",
        previous_snapshot_fingerprint=first.fingerprint,
        files=[_fact("superset-frontend/packages/superset-ui-core/test/query/getClientErrorObject.test.ts")],
    )

    with pytest.raises(RepositorySnapshotError, match="history chain is broken"):
        verify_repository_snapshot_chain([second, first], registry)


def test_snapshot_rejects_unresolved_repository_identity() -> None:
    registry = _registry()
    with pytest.raises(RepositorySnapshotError, match="unresolved repository identity"):
        create_repository_review_snapshot(
            registry,
            registry_entry_id="imported-deep-learning-tutorials",
            reviewed_ref="master",
            commit_sha="1" * 40,
            reviewed_at="2026-08-12T23:55:00+03:00",
            files=[RepositoryFileFact(path="README.md", blob_sha="2" * 40)],
        )


def test_snapshot_rejects_secret_or_generated_file_fact() -> None:
    registry = _registry()
    with pytest.raises(RepositorySnapshotError, match="excluded from learning"):
        create_repository_review_snapshot(
            registry,
            registry_entry_id="discovered-apache-superset",
            reviewed_ref="master",
            commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
            reviewed_at="2026-08-12T23:55:00+03:00",
            files=[RepositoryFileFact(path="config/.env.production", blob_sha="2" * 40)],
        )


def test_snapshot_tampering_breaks_fingerprint() -> None:
    registry = _registry()
    snapshot = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:55:00+03:00",
        files=[_fact()],
    )
    tampered = replace(snapshot, reviewed_ref="forged-ref")

    with pytest.raises(RepositorySnapshotError, match="fingerprint mismatch"):
        verify_repository_review_snapshot(tampered, registry)


def test_snapshot_is_invalid_after_registry_version_changes() -> None:
    registry = _registry()
    snapshot = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:55:00+03:00",
        files=[_fact()],
    )
    changed_registry = replace(registry, fingerprint="0" * 64)

    with pytest.raises(RepositorySnapshotError, match="different registry version"):
        verify_repository_review_snapshot(snapshot, changed_registry)


def test_export_is_deterministic_and_contains_no_runtime_authority() -> None:
    registry = _registry()
    snapshot = create_repository_review_snapshot(
        registry,
        registry_entry_id="discovered-apache-superset",
        reviewed_ref="master",
        commit_sha="cc35056bc96df40e0b0d565c09c665d74a8e74ea",
        reviewed_at="2026-08-12T23:55:00+03:00",
        files=[_fact()],
    )

    exported = export_repository_review_snapshot(snapshot)
    assert exported == export_repository_review_snapshot(snapshot)
    assert '"repository": "apache/superset"' in exported
    assert "token" not in exported.lower()
    assert "credential" not in exported.lower()
