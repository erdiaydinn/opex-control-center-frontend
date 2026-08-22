from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.frontier3_certification_intelligence import (
    BenchmarkProtocolIdentity,
    BenchmarkScenarioCoverage,
    Frontier3CertificationArtifact,
    Frontier3CertificationPolicy,
    Frontier3MatrixDisposition,
    FrontierCertificationDomain,
    FrontierCertificationStatus,
    FrontierSystemMeasurement,
    JarvisDomainMeasurement,
    certify_frontier3_matrix,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
JARVIS_VERSION = "jarvis-v-next"


def coverage(**overrides) -> BenchmarkScenarioCoverage:
    values = {
        "holdout": True,
        "out_of_distribution": True,
        "adversarial": True,
        "temporal": True,
    }
    values.update(overrides)
    return BenchmarkScenarioCoverage(**values)


def protocol(domain: FrontierCertificationDomain, *, version: str = "v1") -> BenchmarkProtocolIdentity:
    suffix = domain.value.replace("_", "-")
    return BenchmarkProtocolIdentity(
        protocol_id=f"frontier3-{suffix}",
        protocol_version=version,
        task_set_id=f"taskset-{suffix}",
        task_set_fingerprint="a" * 64,
        environment_fingerprint="b" * 64,
        metric_set_fingerprint="c" * 64,
    )


def jarvis_measurement(
    domain: FrontierCertificationDomain,
    *,
    score: float = 0.97,
    lower: float = 0.95,
    upper: float = 0.99,
    sample_count: int = 240,
    measured_at: datetime = NOW - timedelta(days=1),
    scenario_coverage: BenchmarkScenarioCoverage | None = None,
    protocol_version: str = "v1",
    evaluator: str | None = None,
    safety_regression: bool = False,
    version: str = JARVIS_VERSION,
) -> JarvisDomainMeasurement:
    return JarvisDomainMeasurement(
        measurement_id=f"jarvis-{domain.value}",
        domain=domain,
        system_version=version,
        normalized_score=score,
        confidence_lower=lower,
        confidence_upper=upper,
        confidence_level=0.95,
        sample_count=sample_count,
        measured_at=measured_at,
        protocol=protocol(domain, version=protocol_version),
        scenario_coverage=scenario_coverage or coverage(),
        independent_evaluator_ref=evaluator or f"eval-jarvis-{domain.value}",
        evidence_refs=(
            f"benchmark://jarvis/{domain.value}/run",
            f"benchmark://jarvis/{domain.value}/review",
        ),
        critical_safety_regression=safety_regression,
    )


def frontier_measurements(
    domain: FrontierCertificationDomain,
    *,
    scores: tuple[float, float, float] = (0.93, 0.95, 0.97),
    uppers: tuple[float, float, float] = (0.95, 0.97, 0.98),
    sample_count: int = 240,
    measured_at: datetime = NOW - timedelta(days=1),
    scenario_coverage: BenchmarkScenarioCoverage | None = None,
    protocol_versions: tuple[str, str, str] = ("v1", "v1", "v1"),
    evaluators: tuple[str, str, str] | None = None,
    qualified: tuple[bool, bool, bool] = (True, True, True),
    providers: tuple[str, str, str] = ("provider-a", "provider-b", "provider-c"),
) -> tuple[FrontierSystemMeasurement, ...]:
    evaluator_values = evaluators or tuple(
        f"eval-peer-{idx}-{domain.value}" for idx in range(1, 4)
    )
    systems = ("frontier-a", "frontier-b", "frontier-c")
    lowers = tuple(max(0.0, score - 0.02) for score in scores)
    return tuple(
        FrontierSystemMeasurement(
            measurement_id=f"peer-{idx}-{domain.value}",
            domain=domain,
            system_id=system,
            system_version=f"{system}-2026-08",
            provider_family=provider,
            normalized_score=score,
            confidence_lower=lower,
            confidence_upper=upper,
            confidence_level=0.95,
            sample_count=sample_count,
            measured_at=measured_at,
            protocol=protocol(domain, version=protocol_version),
            scenario_coverage=scenario_coverage or coverage(),
            independent_evaluator_ref=evaluator,
            frontier_qualification_evidence_ref=f"frontier://qualification/{system}",
            evidence_refs=(
                f"benchmark://{system}/{domain.value}/run",
                f"benchmark://{system}/{domain.value}/review",
            ),
            frontier_qualified=is_qualified,
        )
        for idx, (
            system,
            provider,
            score,
            lower,
            upper,
            protocol_version,
            evaluator,
            is_qualified,
        ) in enumerate(
            zip(
                systems,
                providers,
                scores,
                lowers,
                uppers,
                protocol_versions,
                evaluator_values,
                qualified,
                strict=True,
            ),
            start=1,
        )
    )


def focused_policy(domain: FrontierCertificationDomain) -> Frontier3CertificationPolicy:
    return Frontier3CertificationPolicy(required_domains=(domain,))


def certify_one(
    domain: FrontierCertificationDomain = FrontierCertificationDomain.GENERAL_REASONING,
    *,
    jarvis: JarvisDomainMeasurement | None = None,
    peers: tuple[FrontierSystemMeasurement, ...] | None = None,
    assessed_at: datetime = NOW,
    policy: Frontier3CertificationPolicy | None = None,
) -> Frontier3CertificationArtifact:
    return certify_frontier3_matrix(
        certification_id="cert-1",
        tenant_id="tenant-a",
        company_id="company-a",
        jarvis_system_id="jarvis",
        jarvis_system_version=JARVIS_VERSION,
        assessed_at=assessed_at,
        jarvis_measurements=(jarvis or jarvis_measurement(domain),),
        frontier_measurements=peers or frontier_measurements(domain),
        policy=policy or focused_policy(domain),
    )


def test_frontier_parity_uses_strongest_peer_not_average() -> None:
    domain = FrontierCertificationDomain.GENERAL_REASONING
    result = certify_one(
        domain,
        jarvis=jarvis_measurement(domain, score=0.95, lower=0.93, upper=0.97),
        peers=frontier_measurements(
            domain,
            scores=(0.90, 0.91, 0.99),
            uppers=(0.92, 0.93, 1.0),
        ),
    )
    item = result.domain_certifications[0]
    assert item.strongest_frontier_score == 0.99
    assert item.strongest_frontier_system_id == "frontier-c"
    assert item.status is FrontierCertificationStatus.BELOW_FRONTIER
    assert "frontier3_jarvis_below_strongest_frontier" in item.blockers
    assert result.disposition is Frontier3MatrixDisposition.HOLD
    assert result.bounded_matrix_parity_claim_allowed is False


def test_equal_or_higher_raw_score_with_overlapping_intervals_is_bounded_parity_only() -> None:
    domain = FrontierCertificationDomain.SOFTWARE_ENGINEERING
    result = certify_one(domain)
    item = result.domain_certifications[0]
    assert item.status is FrontierCertificationStatus.FRONTIER_PARITY
    assert item.bounded_parity_claim_allowed is True
    assert item.bounded_measured_superiority_claim_allowed is False
    assert result.disposition is Frontier3MatrixDisposition.CERTIFIED
    assert result.complete_frontier3_matrix is False
    assert result.bounded_matrix_measured_superiority_claim_allowed is False
    assert result.universal_superiority_claim_allowed is False


def test_statistical_superiority_requires_lower_bound_above_every_peer_upper_bound() -> None:
    domain = FrontierCertificationDomain.NOVEL_PROBLEM_SOLVING
    result = certify_one(
        domain,
        jarvis=jarvis_measurement(domain, score=0.995, lower=0.985, upper=1.0),
        peers=frontier_measurements(
            domain,
            scores=(0.92, 0.94, 0.96),
            uppers=(0.95, 0.97, 0.98),
        ),
    )
    item = result.domain_certifications[0]
    assert item.status is FrontierCertificationStatus.STATISTICALLY_SUPERIOR
    assert item.bounded_measured_superiority_claim_allowed is True
    assert result.bounded_matrix_measured_superiority_claim_allowed is False


def test_raw_score_above_strongest_is_not_called_superior_when_confidence_intervals_overlap() -> None:
    domain = FrontierCertificationDomain.DEEP_RESEARCH
    result = certify_one(
        domain,
        jarvis=jarvis_measurement(domain, score=0.98, lower=0.955, upper=0.995),
        peers=frontier_measurements(
            domain,
            scores=(0.92, 0.94, 0.97),
            uppers=(0.96, 0.975, 0.985),
        ),
    )
    item = result.domain_certifications[0]
    assert item.status is FrontierCertificationStatus.FRONTIER_PARITY
    assert item.bounded_measured_superiority_claim_allowed is False


def test_three_distinct_provider_families_are_mandatory() -> None:
    domain = FrontierCertificationDomain.GENERAL_KNOWLEDGE
    result = certify_one(
        domain,
        peers=frontier_measurements(
            domain,
            providers=("provider-a", "provider-b", "provider-b"),
        ),
    )
    item = result.domain_certifications[0]
    assert item.status is FrontierCertificationStatus.HOLD
    assert "frontier3_provider_diversity_insufficient" in item.blockers
    assert "frontier3_peer_provider_family_must_be_unique" in item.blockers


def test_same_protocol_taskset_environment_and_metric_identity_is_mandatory() -> None:
    domain = FrontierCertificationDomain.MULTIMODAL_WORLD
    result = certify_one(
        domain,
        peers=frontier_measurements(
            domain,
            protocol_versions=("v1", "v2", "v1"),
        ),
    )
    item = result.domain_certifications[0]
    assert item.status is FrontierCertificationStatus.HOLD
    assert "frontier3_protocol_mismatch:frontier-b" in item.blockers


def test_stale_future_underpowered_or_incomplete_measurements_fail_closed() -> None:
    domain = FrontierCertificationDomain.LIVE_WORLD_KNOWLEDGE
    stale = certify_one(
        domain,
        peers=frontier_measurements(domain, measured_at=NOW - timedelta(days=31)),
    )
    assert any("benchmark_stale" in code for code in stale.domain_certifications[0].blockers)

    future = certify_one(
        domain,
        jarvis=jarvis_measurement(domain, measured_at=NOW + timedelta(minutes=1)),
    )
    assert "frontier3_jarvis_future_measurement_forbidden" in future.domain_certifications[0].blockers

    underpowered = certify_one(
        domain,
        peers=frontier_measurements(domain, sample_count=20),
    )
    assert any("sample_count_insufficient" in code for code in underpowered.domain_certifications[0].blockers)

    incomplete = certify_one(
        domain,
        peers=frontier_measurements(
            domain,
            scenario_coverage=coverage(temporal=False),
        ),
    )
    assert any("scenario_coverage_incomplete" in code for code in incomplete.domain_certifications[0].blockers)


def test_evaluators_must_be_independent_across_jarvis_and_frontier_measurements() -> None:
    domain = FrontierCertificationDomain.SELF_CORRECTION
    jarvis = jarvis_measurement(domain, evaluator="same-evaluator")
    peers = frontier_measurements(
        domain,
        evaluators=("same-evaluator", "peer-two", "peer-three"),
    )
    result = certify_one(domain, jarvis=jarvis, peers=peers)
    item = result.domain_certifications[0]
    assert "frontier3_evaluator_independence_missing:frontier-a" in item.blockers
    assert item.status is FrontierCertificationStatus.HOLD


def test_frontier_qualification_and_critical_safety_regression_are_hard_gates() -> None:
    domain = FrontierCertificationDomain.LONG_CONTEXT
    unqualified = certify_one(
        domain,
        peers=frontier_measurements(domain, qualified=(True, False, True)),
    )
    assert "frontier3_peer_not_frontier_qualified:frontier-b" in unqualified.domain_certifications[0].blockers

    unsafe = certify_one(
        domain,
        jarvis=jarvis_measurement(domain, safety_regression=True),
    )
    assert "frontier3_jarvis_critical_safety_regression" in unsafe.domain_certifications[0].blockers


def test_full_matrix_requires_every_domain_and_only_then_allows_matrix_level_claim() -> None:
    jarvis = tuple(jarvis_measurement(domain) for domain in FrontierCertificationDomain)
    peers = tuple(
        measurement
        for domain in FrontierCertificationDomain
        for measurement in frontier_measurements(domain)
    )
    result = certify_frontier3_matrix(
        certification_id="complete-matrix",
        tenant_id="tenant-a",
        company_id="company-a",
        jarvis_system_id="jarvis",
        jarvis_system_version=JARVIS_VERSION,
        assessed_at=NOW,
        jarvis_measurements=jarvis,
        frontier_measurements=peers,
    )
    assert result.complete_frontier3_matrix is True
    assert result.disposition is Frontier3MatrixDisposition.CERTIFIED
    assert result.certified_domain_count == len(tuple(FrontierCertificationDomain))
    assert result.bounded_matrix_parity_claim_allowed is True
    assert result.bounded_matrix_measured_superiority_claim_allowed is False
    assert result.universal_superiority_claim_allowed is False
    assert result.execution_authority_granted is False


def test_full_matrix_measured_superiority_requires_every_domain_to_clear_confidence_separation() -> None:
    jarvis = tuple(
        jarvis_measurement(domain, score=0.995, lower=0.985, upper=1.0)
        for domain in FrontierCertificationDomain
    )
    peers = tuple(
        measurement
        for domain in FrontierCertificationDomain
        for measurement in frontier_measurements(
            domain,
            scores=(0.91, 0.93, 0.95),
            uppers=(0.94, 0.96, 0.98),
        )
    )
    result = certify_frontier3_matrix(
        certification_id="superior-matrix",
        tenant_id="tenant-a",
        company_id="company-a",
        jarvis_system_id="jarvis",
        jarvis_system_version=JARVIS_VERSION,
        assessed_at=NOW,
        jarvis_measurements=jarvis,
        frontier_measurements=peers,
    )
    assert result.disposition is Frontier3MatrixDisposition.CERTIFIED
    assert result.superiority_domain_count == len(tuple(FrontierCertificationDomain))
    assert result.bounded_matrix_measured_superiority_claim_allowed is True
    assert result.universal_superiority_claim_allowed is False
    assert result.company_truth_promoted is False
    assert result.automatic_model_weight_update_allowed is False
    assert result.automatic_policy_update_allowed is False
    assert result.side_effect_authority_granted is False


def test_missing_required_domain_holds_complete_matrix() -> None:
    domains = tuple(FrontierCertificationDomain)
    jarvis = tuple(jarvis_measurement(domain) for domain in domains[:-1])
    peers = tuple(
        measurement
        for domain in domains[:-1]
        for measurement in frontier_measurements(domain)
    )
    result = certify_frontier3_matrix(
        certification_id="missing-domain",
        tenant_id="tenant-a",
        company_id="company-a",
        jarvis_system_id="jarvis",
        jarvis_system_version=JARVIS_VERSION,
        assessed_at=NOW,
        jarvis_measurements=jarvis,
        frontier_measurements=peers,
    )
    missing = result.domain_certifications[-1]
    assert missing.status is FrontierCertificationStatus.HOLD
    assert missing.blockers == ("frontier3_jarvis_domain_measurement_missing",)
    assert result.disposition is Frontier3MatrixDisposition.HOLD


def test_duplicate_measurement_ids_and_jarvis_version_drift_are_rejected() -> None:
    domain = FrontierCertificationDomain.BUSINESS_DOMAIN_REASONING
    peer = frontier_measurements(domain)[0]
    with pytest.raises(ValueError, match="frontier3_peer_measurement_ids_must_be_unique"):
        certify_frontier3_matrix(
            certification_id="dup",
            tenant_id="tenant-a",
            company_id="company-a",
            jarvis_system_id="jarvis",
            jarvis_system_version=JARVIS_VERSION,
            assessed_at=NOW,
            jarvis_measurements=(jarvis_measurement(domain),),
            frontier_measurements=(peer, peer),
            policy=focused_policy(domain),
        )

    with pytest.raises(ValueError, match="frontier3_jarvis_system_version_mismatch"):
        certify_one(domain, jarvis=jarvis_measurement(domain, version="wrong-version"))


def test_policy_cannot_disable_required_scenario_coverage() -> None:
    with pytest.raises(
        ValueError,
        match="frontier3_complete_scenario_coverage_cannot_be_disabled",
    ):
        Frontier3CertificationPolicy(require_complete_scenario_coverage=False)


def test_artifact_tampering_and_authority_escalation_are_rejected() -> None:
    result = certify_one()
    tampered = result.model_copy(update={"certified_domain_count": 0})
    with pytest.raises(ValueError, match="frontier3_certification_fingerprint_mismatch"):
        Frontier3CertificationArtifact.model_validate(tampered.model_dump(mode="json"))

    escalated = result.model_copy(update={"execution_authority_granted": True})
    with pytest.raises(
        ValueError,
        match="frontier3_certification_never_mints_universal_or_execution_authority",
    ):
        Frontier3CertificationArtifact.model_validate(escalated.model_dump(mode="json"))
