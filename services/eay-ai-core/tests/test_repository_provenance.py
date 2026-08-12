from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.repository_intelligence import load_repository_registry
from app.repository_provenance import build_repository_snapshot, make_repository_fact


REGISTRY = load_repository_registry()


def reviewed_entry_id() -> str:
    for entry in REGISTRY.repositories:
        if entry.identity and entry.review.commit and entry.review.ref:
            return entry.id
    pytest.skip("registry has no commit-pinned reviewed repository yet")


def test_fact_is_bound_to_registry_repository_ref_commit_file_and_symbol():
    entry = REGISTRY.by_id()[reviewed_entry_id()]
    fact = make_repository_fact(
        registry=REGISTRY,
        repository_id=entry.id,
        ref=entry.review.ref,
        commit_sha=entry.review.commit,
        path="src/example.py",
        symbol="Example.contract",
        kind="api-contract",
        contract="Example.contract requires tenant-scoped authorization.",
        content=b"def contract(): pass\n",
        observed_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert fact.coordinate.repository == entry.identity
    assert fact.coordinate.commit_sha == entry.review.commit
    assert fact.symbol == "Example.contract"
    assert len(fact.fingerprint()) == 64


def test_unverified_pending_repository_cannot_enter_project_memory():
    unresolved = next(entry for entry in REGISTRY.repositories if entry.identity is None)
    with pytest.raises(ValueError, match="unverified_identity"):
        make_repository_fact(
            registry=REGISTRY,
            repository_id=unresolved.id,
            ref="main",
            commit_sha="0" * 40,
            path="README.md",
            kind="documentation",
            contract="not trusted",
            content=b"x",
        )


def test_sensitive_and_generated_paths_are_rejected():
    entry = REGISTRY.by_id()[reviewed_entry_id()]
    kwargs = dict(
        registry=REGISTRY,
        repository_id=entry.id,
        ref=entry.review.ref,
        commit_sha=entry.review.commit,
        kind="code",
        contract="safe contract",
        content=b"x",
    )
    with pytest.raises(ValueError, match="sensitive_path"):
        make_repository_fact(path="services/api/.env", **kwargs)
    with pytest.raises(ValueError, match="generated_or_vendor"):
        make_repository_fact(path="node_modules/pkg/index.js", **kwargs)


def test_reviewed_ref_and_commit_are_fail_closed():
    entry = REGISTRY.by_id()[reviewed_entry_id()]
    with pytest.raises(ValueError, match="commit_not_reviewed"):
        make_repository_fact(
            registry=REGISTRY,
            repository_id=entry.id,
            ref=entry.review.ref,
            commit_sha="f" * 40,
            path="src/example.py",
            kind="code",
            contract="wrong commit",
            content=b"x",
        )


def test_temporal_supersession_preserves_history_and_latest_view():
    entry = REGISTRY.by_id()[reviewed_entry_id()]
    first = make_repository_fact(
        registry=REGISTRY,
        repository_id=entry.id,
        ref=entry.review.ref,
        commit_sha=entry.review.commit,
        path="src/rule.py",
        symbol="RULE",
        kind="kpi-rule",
        contract="Rule version 1",
        content=b"RULE=1",
        observed_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    second = make_repository_fact(
        registry=REGISTRY,
        repository_id=entry.id,
        ref=entry.review.ref,
        commit_sha=entry.review.commit,
        path="src/rule.py",
        symbol="RULE",
        kind="kpi-rule",
        contract="Rule version 2",
        content=b"RULE=2",
        observed_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        supersedes_fingerprint=first.fingerprint(),
    )
    snapshot = build_repository_snapshot(registry=REGISTRY, facts=[first, second])
    assert len(snapshot.facts) == 2
    assert snapshot.latest_facts() == [second]
    assert len(snapshot.fingerprint()) == 64


def test_snapshot_rejects_coordinate_identity_drift():
    entry = REGISTRY.by_id()[reviewed_entry_id()]
    fact = make_repository_fact(
        registry=REGISTRY,
        repository_id=entry.id,
        ref=entry.review.ref,
        commit_sha=entry.review.commit,
        path="README.md",
        kind="documentation",
        contract="Pinned documentation",
        content=b"x",
    )
    fact.coordinate.repository = "attacker/replaced-repo"
    with pytest.raises(ValueError, match="identity_drift"):
        build_repository_snapshot(registry=REGISTRY, facts=[fact])
