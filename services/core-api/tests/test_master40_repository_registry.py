from pathlib import Path

from app.repository_intelligence.registry import (
    REQUIRED_SEED_IDS,
    RepositoryEntry,
    assert_registry_preserves_required_seeds,
    load_registry,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "docs/governance/eay_repository_intelligence_registry.json"


def test_registry_preserves_all_required_sources_without_guessing_unresolved_identity() -> None:
    entries = load_registry(REGISTRY_PATH)
    assert_registry_preserves_required_seeds(entries)
    assert {entry.registry_id for entry in entries} >= REQUIRED_SEED_IDS
    assert {entry.classification for entry in entries} == {
        "OWN",
        "IMPORTED",
        "DISCOVERED",
    }

    unresolved = [entry for entry in entries if entry.identity_status == "UNRESOLVED"]
    assert unresolved
    assert all(entry.repository is None for entry in unresolved)
    assert all(entry.canonical_upstream is None for entry in unresolved)
    assert all(entry.source_locator for entry in unresolved)
    assert all(not entry.analysis_permitted for entry in unresolved)
    assert all(not entry.usable_as_code_source for entry in unresolved)


def test_own_sources_are_code_authoritative_but_pending_external_sources_are_not() -> None:
    entries = {entry.registry_id: entry for entry in load_registry(REGISTRY_PATH)}
    for registry_id in (
        "own:opex-control-center-frontend",
        "own:planai-audit",
        "own:adaronya",
    ):
        assert entries[registry_id].usable_as_code_source

    council = entries["imported:council-of-high-intelligence"]
    assert council.analysis_permitted
    assert not council.usable_as_code_source

    superset = entries["discovered:superset"]
    assert superset.analysis_permitted
    assert not superset.usable_as_code_source


def test_restrictive_reference_can_be_analyzed_but_never_adopted_as_code() -> None:
    reference = RepositoryEntry(
        registry_id="discovered:restrictive-example",
        classification="DISCOVERED",
        repository="owner/restrictive",
        identity_status="VERIFIED",
        canonical_upstream="owner/restrictive",
        relation="REFERENCE_ONLY",
        license_status="REFERENCE_ONLY_RESTRICTIVE",
        decision="REFERENCE",
        security_relevance="MEDIUM",
    )
    assert reference.analysis_permitted
    assert not reference.usable_as_code_source


def test_superset_canonical_and_localization_derivative_are_not_conflated() -> None:
    entries = {entry.registry_id: entry for entry in load_registry(REGISTRY_PATH)}
    assert entries["discovered:superset"].repository == "apache/superset"
    assert entries["discovered:superset-tr"].canonical_upstream == "apache/superset"
    assert (
        entries["discovered:superset-tr"].relation
        == "LOCALIZATION_VENDOR_DERIVATIVE"
    )


def test_discovered_capability_categories_remain_explicit_when_exact_repos_are_unresolved() -> None:
    entries = {entry.registry_id: entry for entry in load_registry(REGISTRY_PATH)}
    expected = {
        "discovered:local-llm-serving-set",
        "discovered:agent-orchestration-set",
        "discovered:rag-retrieval-set",
        "discovered:evaluation-set",
        "discovered:observability-set",
        "discovered:vision-document-set",
        "discovered:model-registry-lifecycle-set",
        "discovered:workflow-automation-set",
        "discovered:security-guardrails-set",
        "discovered:fine-tuning-set",
        "discovered:data-catalog-semantic-set",
        "discovered:jarvis-evolution-set",
    }
    assert set(entries) >= expected
    assert all(entries[key].identity_status == "UNRESOLVED" for key in expected)
