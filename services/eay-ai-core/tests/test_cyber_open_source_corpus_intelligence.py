from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cyber_open_source_corpus import (
    CorpusIngestionMode,
    CorpusSnapshotReceipt,
    CorpusSource,
    CorpusTrustClass,
    IngestionDisposition,
    evaluate_corpus_snapshot,
    load_corpus_registry,
)

CONFIG = Path(__file__).parents[1] / "config" / "cyber_open_source_corpus.json"


def registry():
    return load_corpus_registry(CONFIG)


def by_id(source_id: str):
    return next(item for item in registry().sources if item.source_id == source_id)


def receipt(source: CorpusSource, **overrides: object) -> CorpusSnapshotReceipt:
    values: dict[str, object] = {
        "source_id": source.source_id,
        "owner_repo": source.owner_repo,
        "commit_sha": "a" * 40,
        "content_fingerprint": "b" * 64,
        "license_verified": True,
        "provenance_verified": True,
        "security_reviewed": True,
        "archived_observed": source.archived,
    }
    values.update(overrides)
    return CorpusSnapshotReceipt.model_validate(values)


def test_curated_registry_contains_user_sources_and_strong_defensive_expansion():
    source_ids = {item.source_id for item in registry().sources}
    assert len(source_ids) >= 40
    assert {
        "paulveillard-cybersecurity",
        "carterperez-cybersecurity-projects",
        "ultimate-cybersecurity-resources",
        "awesome-hacking",
        "awesome-pentest",
        "hacker-roadmap",
        "payloads-all-the-things",
    } <= source_ids
    assert {
        "sigma-rules",
        "misp",
        "opencti",
        "atomic-red-team",
        "mitre-caldera",
        "falco",
        "trivy",
        "prowler",
        "kubescape",
        "tetragon",
        "syft",
        "grype",
        "cosign",
        "slsa",
        "osv-scanner",
        "semgrep",
        "codeql",
        "owasp-zap",
        "defectdojo",
        "dependency-track",
        "nuclei",
        "nuclei-templates",
        "garak",
        "pyrit",
        "promptfoo",
        "purplellama",
    } <= source_ids


def test_external_corpus_never_mints_company_or_execution_authority():
    for source in registry().sources:
        assert source.company_truth_authority is False
        assert source.incident_confirmation_authority is False
        assert source.execution_authority_granted is False
        assert source.production_execution_allowed is False
        assert source.normal_chat_execution_allowed is False
        assert source.auto_trust_linked_sources is False
        assert source.allow_code_reuse is False


def test_meta_indexes_are_discovery_only_and_never_auto_trust_links():
    for source_id in ("awesome-hacking", "ultimate-cybersecurity-resources"):
        source = by_id(source_id)
        assert source.meta_index is True
        assert source.ingestion_mode is CorpusIngestionMode.INDEX_ONLY
        assert source.auto_trust_linked_sources is False


def test_archived_roadmap_cannot_support_current_security_truth():
    source = by_id("hacker-roadmap")
    assert source.archived is True
    assert source.supports_current_state_claim is False


def test_restricted_adversarial_sources_are_quarantined_from_normal_rag():
    restricted = [
        item
        for item in registry().sources
        if item.trust_class is CorpusTrustClass.L4_ADVERSARIAL_RESTRICTED
    ]
    assert {item.source_id for item in restricted} >= {
        "payloads-all-the-things",
        "atomic-red-team",
        "mitre-caldera",
        "nuclei-templates",
    }
    for source in restricted:
        assert source.allow_normal_rag is False
        assert source.allow_sandbox_execution is True
        assert source.sandbox_required is True
        assert source.ingestion_mode is CorpusIngestionMode.SANDBOX_CORPUS


def test_restricted_payload_snapshot_requires_authorized_sandbox():
    source = by_id("payloads-all-the-things")
    decision = evaluate_corpus_snapshot(source=source, receipt=receipt(source))
    assert decision.disposition is IngestionDisposition.QUARANTINE
    assert "restricted_source_authorized_sandbox_required" in decision.blockers
    assert decision.sandbox_execution_allowed is False
    assert decision.normal_rag_allowed is False


def test_restricted_payload_snapshot_can_only_enter_existing_authorized_sandbox():
    source = by_id("payloads-all-the-things")
    decision = evaluate_corpus_snapshot(
        source=source,
        receipt=receipt(source),
        authorized_sandbox=True,
    )
    assert decision.disposition is IngestionDisposition.READY
    assert decision.sandbox_execution_allowed is True
    assert decision.normal_rag_allowed is False
    assert decision.company_truth_promoted is False
    assert decision.execution_authority_granted is False
    assert decision.production_execution_allowed is False


def test_unverified_license_or_provenance_holds_defensive_source():
    source = by_id("sigma-rules")
    decision = evaluate_corpus_snapshot(
        source=source,
        receipt=receipt(
            source,
            license_verified=False,
            provenance_verified=False,
        ),
    )
    assert decision.disposition is IngestionDisposition.HOLD
    assert "source_license_review_missing" in decision.blockers
    assert "source_provenance_unverified" in decision.blockers


def test_snapshot_identity_swap_is_rejected():
    source = by_id("misp")
    decision = evaluate_corpus_snapshot(
        source=source,
        receipt=receipt(source, owner_repo="attacker/replacement"),
    )
    assert decision.disposition is IngestionDisposition.HOLD
    assert "source_snapshot_identity_mismatch" in decision.blockers


def test_agpl_training_repository_cannot_become_product_code_reuse_authority():
    source = by_id("carterperez-cybersecurity-projects")
    assert source.license_spdx == "AGPL-3.0"
    assert source.license_review_required is True
    assert source.allow_code_reuse is False


def test_l4_cannot_be_reconfigured_for_normal_rag_or_without_sandbox():
    with pytest.raises(ValidationError):
        CorpusSource(
            source_id="unsafe",
            owner_repo="example/unsafe",
            trust_class=CorpusTrustClass.L4_ADVERSARIAL_RESTRICTED,
            ingestion_mode=CorpusIngestionMode.SANDBOX_CORPUS,
            domains=("payloads",),
            license_spdx="MIT",
            allow_normal_rag=True,
            allow_sandbox_execution=True,
            sandbox_required=True,
        )
    with pytest.raises(ValidationError):
        CorpusSource(
            source_id="unsafe2",
            owner_repo="example/unsafe2",
            trust_class=CorpusTrustClass.L4_ADVERSARIAL_RESTRICTED,
            ingestion_mode=CorpusIngestionMode.SANDBOX_CORPUS,
            domains=("payloads",),
            license_spdx="MIT",
            allow_normal_rag=False,
            allow_sandbox_execution=False,
            sandbox_required=False,
        )


def test_meta_index_cannot_silently_become_bulk_ingestion_source():
    with pytest.raises(ValidationError):
        CorpusSource(
            source_id="bad-meta",
            owner_repo="example/meta",
            trust_class=CorpusTrustClass.L1_CURATED_DEFENSIVE,
            ingestion_mode=CorpusIngestionMode.PINNED_CONTENT,
            domains=("discovery",),
            license_spdx="CC0-1.0",
            meta_index=True,
        )
