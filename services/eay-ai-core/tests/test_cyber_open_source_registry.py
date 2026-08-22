from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cyber_open_source_registry import (
    CyberOpenSourceRepository,
    OpenSourceAdmission,
    OpenSourceRiskClass,
    OpenSourceUseMode,
    assess_repository_admission,
    load_registry,
)

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "cyber_open_source_registry.json"
PIN = "a" * 40


def registry():
    return load_registry(REGISTRY_PATH)


def by_repo(name: str) -> CyberOpenSourceRepository:
    return next(item for item in registry().repositories if item.repo == name)


def test_registry_is_large_diverse_unique_and_fingerprint_sealed():
    value = registry()
    assert len(value.repositories) >= 40
    assert len({item.repo.lower() for item in value.repositories}) == len(value.repositories)
    assert len(value.fingerprint) == 64
    assert all(len(item.fingerprint) == 64 for item in value.repositories)

    required = {
        "SigmaHQ/sigma",
        "Velocidex/velociraptor",
        "zeek/zeek",
        "OISF/suricata",
        "falcosecurity/falco",
        "cilium/tetragon",
        "aquasecurity/trivy",
        "google/osv-scanner",
        "anchore/syft",
        "sigstore/cosign",
        "in-toto/in-toto",
        "ossf/scorecard",
        "kyverno/kyverno",
        "open-policy-agent/gatekeeper",
        "kubescape/kubescape",
        "NVIDIA/garak",
        "Azure/PyRIT",
        "mitre/caldera",
        "redcanaryco/atomic-red-team",
        "projectdiscovery/nuclei",
    }
    assert required <= {item.repo for item in value.repositories}


def test_every_repository_is_server_side_reviewed_pinned_and_never_privileged():
    for item in registry().repositories:
        assert item.server_side_only is True
        assert item.upstream_pin_required is True
        assert item.license_review_required is True
        assert item.security_review_required is True
        assert item.content_vendoring_permitted is False
        assert item.production_execution_permitted is False
        assert item.production_mutation_permitted is False
        assert item.credential_access_permitted is False
        assert item.offensive_execution_permitted is False
        assert item.unrestricted_network_permitted is False


def test_dual_use_sources_are_sandbox_only():
    dual_use = [
        item for item in registry().repositories if item.risk_class is OpenSourceRiskClass.DUAL_USE
    ]
    assert dual_use
    assert all(item.use_mode is OpenSourceUseMode.AUTHORIZED_SANDBOX_ONLY for item in dual_use)


def test_reference_only_never_needs_execution_to_be_useful():
    decision = assess_repository_admission(by_repo("wazuh/wazuh"))
    assert decision.admission is OpenSourceAdmission.REFERENCE_ADMITTED
    assert decision.blockers == ()
    assert decision.execution_authority_granted is False
    assert decision.production_authority_granted is False


def test_detection_corpus_fails_closed_without_pin_license_and_security_review():
    sigma = by_repo("SigmaHQ/sigma")
    decision = assess_repository_admission(sigma)
    assert decision.admission is OpenSourceAdmission.INGESTION_REVIEW_REQUIRED
    assert decision.blockers == (
        "immutable_upstream_commit_pin_required",
        "license_review_required",
        "security_review_required",
    )


def test_detection_corpus_can_be_admitted_read_only_after_reviews_and_pin():
    sigma = by_repo("SigmaHQ/sigma")
    decision = assess_repository_admission(
        sigma,
        pinned_commit_sha=PIN,
        license_review_passed=True,
        security_review_passed=True,
    )
    assert decision.admission is OpenSourceAdmission.ADMITTED_READ_ONLY
    assert decision.pinned_commit_sha == PIN
    assert decision.blockers == ()
    assert decision.execution_authority_granted is False


def test_ci_tool_requires_isolated_runner_even_after_pin_and_reviews():
    trivy = by_repo("aquasecurity/trivy")
    held = assess_repository_admission(
        trivy,
        pinned_commit_sha=PIN,
        license_review_passed=True,
        security_review_passed=True,
    )
    assert held.admission is OpenSourceAdmission.CI_REVIEW_REQUIRED
    assert held.blockers == ("isolated_runner_verification_required",)

    admitted = assess_repository_admission(
        trivy,
        pinned_commit_sha=PIN,
        license_review_passed=True,
        security_review_passed=True,
        isolated_runner_verified=True,
    )
    assert admitted.admission is OpenSourceAdmission.ADMITTED_CI_ISOLATED
    assert admitted.execution_authority_granted is False
    assert admitted.production_authority_granted is False


def test_dual_use_tool_requires_security_guardian_sandbox_authority():
    nuclei = by_repo("projectdiscovery/nuclei")
    held = assess_repository_admission(
        nuclei,
        pinned_commit_sha=PIN,
        license_review_passed=True,
        security_review_passed=True,
        isolated_runner_verified=True,
    )
    assert held.admission is OpenSourceAdmission.SANDBOX_AUTHORITY_REQUIRED
    assert held.blockers == ("security_guardian_sandbox_authority_required",)

    admitted = assess_repository_admission(
        nuclei,
        pinned_commit_sha=PIN,
        license_review_passed=True,
        security_review_passed=True,
        isolated_runner_verified=True,
        sandbox_authorized=True,
    )
    assert admitted.admission is OpenSourceAdmission.ADMITTED_SANDBOX
    assert admitted.execution_authority_granted is False
    assert admitted.production_authority_granted is False


def test_bad_commit_pin_is_not_preserved_as_evidence():
    trivy = by_repo("aquasecurity/trivy")
    decision = assess_repository_admission(
        trivy,
        pinned_commit_sha="latest",
        license_review_passed=True,
        security_review_passed=True,
        isolated_runner_verified=True,
    )
    assert decision.admission is OpenSourceAdmission.CI_REVIEW_REQUIRED
    assert "immutable_upstream_commit_pin_invalid" in decision.blockers
    assert decision.pinned_commit_sha is None


def test_registry_rejects_dual_use_source_outside_sandbox():
    source = by_repo("projectdiscovery/nuclei")
    payload = source.model_dump(mode="json")
    payload["use_mode"] = OpenSourceUseMode.CI_ISOLATED.value
    with pytest.raises(ValidationError, match="cyber_open_source_dual_use_must_be_sandbox_only"):
        CyberOpenSourceRepository.model_validate(payload)


def test_registry_rejects_any_production_or_credential_authority():
    source = by_repo("aquasecurity/trivy")
    for field in (
        "content_vendoring_permitted",
        "production_execution_permitted",
        "production_mutation_permitted",
        "credential_access_permitted",
        "offensive_execution_permitted",
        "unrestricted_network_permitted",
    ):
        payload = source.model_dump(mode="json")
        payload[field] = True
        with pytest.raises(ValidationError, match="cyber_open_source_never_grants_privileged_authority"):
            CyberOpenSourceRepository.model_validate(payload)
