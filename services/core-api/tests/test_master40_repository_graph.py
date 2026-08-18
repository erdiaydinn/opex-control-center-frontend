import pytest

from app.repository_intelligence.graph import (
    RepoSnapshot,
    build_impact_edges,
    repo_question_context,
    snapshot_usable_as_code_source,
    validate_snapshot_against_registry,
)
from app.repository_intelligence.registry import RepositoryEntry


def snapshot(
    registry_id: str,
    repository: str,
    sha: str,
    contracts: tuple[str, ...],
    *,
    license_status: str = "OWNED",
    decision: str = "OWN",
) -> RepoSnapshot:
    return RepoSnapshot(
        registry_id=registry_id,
        repository=repository,
        commit_sha=sha,
        branch_or_tag="main",
        paths=("service.py",),
        symbols=("Handler",),
        contracts=contracts,
        owners=("platform",),
        license_status=license_status,
        decision=decision,
    )


def own_entry(registry_id: str, repository: str) -> RepositoryEntry:
    return RepositoryEntry(
        registry_id=registry_id,
        classification="OWN",
        repository=repository,
        identity_status="VERIFIED",
        canonical_upstream=None,
        relation="OWN",
        license_status="OWNED",
        decision="OWN",
        security_relevance="HIGH",
    )


def test_impact_graph_is_exact_sha_and_contract_bound() -> None:
    first = snapshot("a", "owner/a", "a" * 40, ("tenant-contract", "orders-v2"))
    second = snapshot("b", "owner/b", "b" * 40, ("orders-v2",))
    edges = build_impact_edges((first, second))
    assert any(
        edge.contract == "orders-v2"
        and edge.source_registry_id == "a"
        and edge.target_registry_id == "b"
        for edge in edges
    )
    assert repo_question_context(
        snapshots=(first, second),
        question_terms=("tenant-contract",),
    ) == (first,)


def test_snapshot_must_match_verified_registry_identity_and_license_decision() -> None:
    entry = own_entry("own:a", "owner/a")
    valid = snapshot("own:a", "owner/a", "a" * 40, ("orders-v2",))
    validate_snapshot_against_registry(valid, entry)
    assert snapshot_usable_as_code_source(valid, entry)

    wrong_repo = snapshot("own:a", "owner/b", "a" * 40, ("orders-v2",))
    with pytest.raises(ValueError, match="repository does not match"):
        validate_snapshot_against_registry(wrong_repo, entry)

    wrong_license = snapshot(
        "own:a",
        "owner/a",
        "a" * 40,
        ("orders-v2",),
        license_status="PENDING_REVIEW",
    )
    with pytest.raises(ValueError, match="license/decision drifted"):
        validate_snapshot_against_registry(wrong_license, entry)


def test_reference_only_snapshot_can_enter_analysis_but_not_code_adoption() -> None:
    entry = RepositoryEntry(
        registry_id="discovered:ref",
        classification="DISCOVERED",
        repository="owner/reference",
        identity_status="VERIFIED",
        canonical_upstream="owner/reference",
        relation="REFERENCE_ONLY",
        license_status="REFERENCE_ONLY_RESTRICTIVE",
        decision="REFERENCE",
        security_relevance="MEDIUM",
    )
    reference = snapshot(
        "discovered:ref",
        "owner/reference",
        "c" * 40,
        ("design-pattern",),
        license_status="REFERENCE_ONLY_RESTRICTIVE",
        decision="REFERENCE",
    )
    validate_snapshot_against_registry(reference, entry)
    assert not snapshot_usable_as_code_source(reference, entry)


def test_invalid_sha_or_empty_question_never_enters_context() -> None:
    with pytest.raises(ValueError, match="commit SHA"):
        repo_question_context(
            snapshots=(snapshot("x", "owner/x", "bad", ()),),
            question_terms=("x",),
        )
    valid = snapshot("x", "owner/x", "d" * 40, ("contract",))
    assert repo_question_context(snapshots=(valid,), question_terms=()) == ()
