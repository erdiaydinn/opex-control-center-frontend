from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.company_context_boundary import build_company_identity
from app.company_cyber_incident_intelligence import (
    IncidentStatus,
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    build_company_security_signal,
)
from app.cyber_attack_path_intelligence import CyberSurfaceKind
from app.cyber_benchmark_intelligence import (
    CyberBenchmarkEvidenceClass,
    default_cyber_benchmark_profile,
)
from app.cyber_continuous_defense_pipeline import (
    CISA_KEV_CANONICAL_URL,
    CISA_KEV_OFFICIAL_MIRROR_URL,
    FIRST_EPSS_API_URL,
    NVD_CVE_API_URL,
    CveAssetMatchStatus,
    EayCveImpactStatus,
    FeedTransport,
    LiveThreatFeedClient,
    LiveThreatSourceUnavailable,
    SandboxEvidenceClass,
    SigmaCoverageStatus,
    SigmaTelemetryStatus,
    assess_eay_cve_impact,
    assess_sigma_coverage,
    build_asset_inventory_snapshot,
    build_asset_observation,
    build_continuous_benchmark_checkpoint,
    build_defensive_recommendations,
    build_dependency_observation,
    build_sigma_rule_metadata,
    build_sigma_telemetry_observation,
    ingest_live_public_threat,
    latest_kev_cve_id,
    materialize_eay_attack_graph,
    run_continuous_defense_cycle,
    triage_company_incident,
    validate_controlled_sandbox,
)
from app.cyber_defense_intelligence import AssetCriticality
from app.jarvis_benchmark import MetricMeasurement

NOW = datetime(2026, 8, 21, 13, 0, tzinfo=UTC)
CVE = "CVE-2026-9001"
CPE = "cpe:2.3:a:example:eay_dependency:1.2.3:*:*:*:*:*:*:*"


def _identity():
    return build_company_identity(
        tenant_id="tenant-a",
        company_id="company-a",
        company_slug="company-a",
        profile_revision="rev-cyber-1",
        environment="production",
    )


def _kev_payload():
    return {
        "catalogVersion": "2026.08.21",
        "dateReleased": "2026-08-21T12:00:00.000Z",
        "count": 1,
        "vulnerabilities": [
            {
                "cveID": CVE,
                "vendorProject": "Example",
                "product": "EAY Dependency",
                "vulnerabilityName": "Example vulnerability",
                "dateAdded": "2026-08-20",
                "shortDescription": "Defensive fixture",
                "requiredAction": "Apply vendor mitigations",
                "dueDate": "2026-09-01",
                "cwes": ["CWE-79"],
            }
        ],
    }


def _nvd_payload():
    return {
        "resultsPerPage": 1,
        "startIndex": 0,
        "totalResults": 1,
        "vulnerabilities": [
            {
                "cve": {
                    "id": CVE,
                    "published": "2026-08-19T10:00:00.000Z",
                    "lastModified": "2026-08-21T10:00:00.000Z",
                    "weaknesses": [
                        {"description": [{"lang": "en", "value": "CWE-79"}]}
                    ],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}
                        ]
                    },
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "cpeMatch": [
                                        {
                                            "vulnerable": True,
                                            "criteria": CPE,
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                }
            }
        ],
    }


def _epss_payload():
    return {
        "status": "OK",
        "status-code": 200,
        "version": "1.0",
        "total": 1,
        "data": [
            {
                "cve": CVE,
                "epss": "0.910000000",
                "percentile": "0.990000000",
                "date": "2026-08-21",
            }
        ],
    }


def _response(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.startswith(NVD_CVE_API_URL):
        return httpx.Response(200, json=_nvd_payload())
    if url.startswith(FIRST_EPSS_API_URL):
        return httpx.Response(200, json=_epss_payload())
    if url == CISA_KEV_CANONICAL_URL:
        return httpx.Response(200, json=_kev_payload())
    if url == CISA_KEV_OFFICIAL_MIRROR_URL:
        return httpx.Response(200, json=_kev_payload())
    return httpx.Response(404, json={"error": "not found"})


def _fallback_response(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == CISA_KEV_CANONICAL_URL:
        return httpx.Response(403, json={"error": "blocked"})
    if url == CISA_KEV_OFFICIAL_MIRROR_URL:
        return httpx.Response(200, json=_kev_payload())
    return _response(request)


def _ingestion(*, fallback: bool = False):
    transport = httpx.MockTransport(_fallback_response if fallback else _response)
    client = LiveThreatFeedClient(transport=transport)
    try:
        return ingest_live_public_threat(client=client, cve_id=CVE, as_of=NOW)
    finally:
        client.close()


def _inventory(*, deployed: bool = True, exact_cpe: bool = True):
    identity = _identity()
    api = build_asset_observation(
        asset_ref="asset:eay-api",
        surface_kind=CyberSurfaceKind.SERVICE,
        criticality=AssetCriticality.CRITICAL,
        evidence_refs=("repo:services/core-api/pyproject.toml",),
        product_refs=("vendor-product:example:eay-dependency",),
        cpe_refs=(CPE,) if exact_cpe else (),
        observed_at=NOW,
        recorded_at=NOW,
        deployment_observed=deployed,
        internet_reachable=True,
    )
    db = build_asset_observation(
        asset_ref="asset:postgres-authority",
        surface_kind=CyberSurfaceKind.DATA_STORE,
        criticality=AssetCriticality.CRITICAL,
        evidence_refs=("repo:services/core-api/alembic",),
        observed_at=NOW,
        recorded_at=NOW,
        deployment_observed=deployed,
        crown_jewel=True,
    )
    dependency = build_dependency_observation(
        relation_id="relation:eay-api-to-postgres",
        from_asset_ref=api.asset_ref,
        to_asset_ref=db.asset_ref,
        evidence_refs=("repo:core-api:postgres-repository",),
        observed_at=NOW,
        recorded_at=NOW,
    )
    return build_asset_inventory_snapshot(
        identity=identity,
        assets=(api, db),
        dependencies=(dependency,),
        as_of=NOW,
        inventory_coverage_complete=False,
        production_deployment_truth_claimed=False,
    )


def _sigma_rule():
    return build_sigma_rule_metadata(
        rule={
            "title": "Example CVE defensive detection metadata",
            "id": "11111111-1111-1111-1111-111111111111",
            "status": "test",
            "level": "high",
            "tags": ["attack.t1059", "cve.2026.9001"],
            "logsource": {"category": "process_creation", "product": "windows"},
            # Detection bodies are deliberately outside this metadata contract.
            "detection": {"selection": {"Image": "example.exe"}},
        },
        evidence_ref="sigmahq:rule:11111111",
    )


def test_live_public_ingestion_keeps_kev_nvd_epss_authorities_separate():
    receipt = _ingestion()

    assert receipt.primary_threat.source.value == "cisa_kev"
    assert receipt.primary_threat.known_exploited_in_wild is True
    assert receipt.known_exploitation_authority_observed is True
    assert receipt.current_nvd_observed is True
    assert receipt.current_epss_observed is True
    assert receipt.epss is not None and receipt.epss.score == pytest.approx(0.91)
    assert receipt.nvd_cpe_refs == (CPE,)
    assert receipt.company_truth_granted is False
    assert receipt.execution_authority_granted is False


def test_cisa_canonical_transport_failure_falls_back_only_to_official_cisagov_mirror():
    receipt = _ingestion(fallback=True)
    kev_observations = [
        item for item in receipt.source_observations if item.source.value == "cisa_kev"
    ]
    assert len(kev_observations) == 1
    assert kev_observations[0].transport is FeedTransport.OFFICIAL_MIRROR
    assert kev_observations[0].canonical_authority_observed is False
    assert receipt.primary_threat.known_exploited_in_wild is True


def test_latest_kev_selection_is_date_based_not_input_order():
    payload = _kev_payload()
    payload["vulnerabilities"].append(
        {
            **payload["vulnerabilities"][0],
            "cveID": "CVE-2026-9002",
            "dateAdded": "2026-08-21",
        }
    )
    assert latest_kev_cve_id(payload) == "CVE-2026-9002"


def test_unknown_or_arbitrary_network_target_is_not_a_supported_public_feed():
    client = LiveThreatFeedClient(transport=httpx.MockTransport(_response))
    try:
        with pytest.raises(ValueError, match="endpoint_not_allowlisted"):
            client._get_json("https://example.com/feed.json")  # noqa: SLF001
    finally:
        client.close()


def test_exact_cpe_plus_deployment_evidence_is_required_for_confirmed_eay_impact():
    ingestion = _ingestion()
    confirmed = assess_eay_cve_impact(
        ingestion=ingestion,
        inventory=_inventory(deployed=True, exact_cpe=True),
        as_of=NOW,
    )
    potential = assess_eay_cve_impact(
        ingestion=ingestion,
        inventory=_inventory(deployed=False, exact_cpe=True),
        as_of=NOW,
    )

    assert confirmed.status is EayCveImpactStatus.CONFIRMED
    assert confirmed.matches[0].status is CveAssetMatchStatus.CONFIRMED
    assert confirmed.firm_company_impact_authorized is True
    assert potential.status is EayCveImpactStatus.POTENTIAL
    assert potential.matches[0].status is CveAssetMatchStatus.POTENTIAL
    assert potential.firm_company_impact_authorized is False


def test_vendor_product_match_without_exact_cpe_cannot_become_confirmed_exposure():
    impact = assess_eay_cve_impact(
        ingestion=_ingestion(),
        inventory=_inventory(deployed=True, exact_cpe=False),
        as_of=NOW,
    )
    assert impact.status is EayCveImpactStatus.POTENTIAL
    assert impact.matches[0].exact_version_or_cpe_match is False
    assert impact.firm_company_impact_authorized is False


def test_no_asset_match_is_explicitly_not_proof_that_eay_is_safe():
    ingestion = _ingestion()
    identity = _identity()
    unrelated = build_asset_observation(
        asset_ref="asset:unrelated",
        surface_kind=CyberSurfaceKind.SERVICE,
        criticality=AssetCriticality.MEDIUM,
        evidence_refs=("repo:unrelated",),
        cpe_refs=("cpe:2.3:a:other:product:1.0:*:*:*:*:*:*:*",),
        observed_at=NOW,
        recorded_at=NOW,
        deployment_observed=True,
    )
    inventory = build_asset_inventory_snapshot(
        identity=identity,
        assets=(unrelated,),
        dependencies=(),
        as_of=NOW,
        inventory_coverage_complete=False,
    )
    impact = assess_eay_cve_impact(ingestion=ingestion, inventory=inventory, as_of=NOW)

    assert impact.status is EayCveImpactStatus.NO_MATCH_OBSERVED
    assert impact.firm_company_impact_authorized is False
    assert impact.no_match_is_not_proof_of_safety is True
    assert "inventory_coverage_incomplete" in impact.reason_codes


def test_evidence_backed_dependency_graph_surfaces_crown_jewel_blast_radius_without_proving_attack():
    inventory = _inventory()
    graph = materialize_eay_attack_graph(
        inventory=inventory,
        affected_entry_refs=("asset:eay-api",),
    )

    assert graph.path_set is not None
    assert graph.blast_radius is not None
    assert graph.blast_radius.reachable_crown_jewel_refs == ("asset:postgres-authority",)
    assert graph.blast_radius.dangerous_path_count == 1
    assert graph.attack_success_proven is False
    assert graph.execution_authority_granted is False


def test_sigma_rule_analysis_reads_metadata_only_and_unknown_telemetry_is_not_a_fake_gap():
    identity = _identity()
    ingestion = _ingestion()
    rule = _sigma_rule()

    unknown = assess_sigma_coverage(
        identity=identity,
        ingestion=ingestion,
        rules=(rule,),
        telemetry=(),
        as_of=NOW,
    )
    assert rule.detection_body_ingested is False
    assert rule.attack_technique_ids == ("T1059",)
    assert rule.cve_ids == (CVE,)
    assert unknown.status is SigmaCoverageStatus.UNVERIFIED
    assert unknown.firm_detection_gap_authorized is False


def test_sigma_explicit_missing_telemetry_can_create_firm_gap_but_never_auto_deploy():
    identity = _identity()
    ingestion = _ingestion()
    rule = _sigma_rule()
    missing = build_sigma_telemetry_observation(
        identity=identity,
        logsource_key=rule.logsource_key,
        status=SigmaTelemetryStatus.MISSING,
        evidence_refs=("company-evidence:windows-process-telemetry-missing",),
        observed_at=NOW,
        recorded_at=NOW,
    )
    coverage = assess_sigma_coverage(
        identity=identity,
        ingestion=ingestion,
        rules=(rule,),
        telemetry=(missing,),
        as_of=NOW,
    )

    assert coverage.status is SigmaCoverageStatus.PARTIAL
    assert coverage.missing_rule_ids == (rule.rule_id,)
    assert coverage.firm_detection_gap_authorized is True
    assert coverage.automatic_rule_deployment_permitted is False
    assert coverage.execution_authority_granted is False


def test_exposure_signal_alone_is_not_an_incident_confirmation():
    identity = _identity()
    ingestion = _ingestion()
    impact = assess_eay_cve_impact(
        ingestion=ingestion,
        inventory=_inventory(),
        as_of=NOW,
    )
    incident = triage_company_incident(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        as_of=NOW,
    )

    assert incident is not None
    assert incident.status is IncidentStatus.UNCONFIRMED
    assert incident.causal_claim_proven is False
    assert incident.threat_actor_attribution_proven is False


def test_verified_detection_plus_independent_vulnerability_evidence_can_confirm_company_incident_review():
    identity = _identity()
    ingestion = _ingestion()
    impact = assess_eay_cve_impact(
        ingestion=ingestion,
        inventory=_inventory(),
        as_of=NOW,
    )
    detection = build_company_security_signal(
        identity=identity,
        signal_id="signal:endpoint:verified-detection",
        signal_type=SecuritySignalType.ANOMALOUS_PROCESS,
        evidence_strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        source_family=SecuritySourceFamily.ENDPOINT,
        evidence_refs=("edr:verified-detection:abc",),
        observed_at=NOW,
        recorded_at=NOW,
        asset_refs=("asset:eay-api",),
        exposure_refs=(impact.exposures[0].exposure_id,),
        threat_record_refs=(ingestion.primary_threat.record_id,),
        attack_technique_ids=("T1059",),
    )
    incident = triage_company_incident(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        as_of=NOW,
        additional_signals=(detection,),
    )

    assert incident is not None
    assert incident.status is IncidentStatus.CONFIRMED
    assert incident.causal_claim_proven is False
    assert incident.threat_actor_attribution_proven is False
    assert incident.execution_authority_granted is False


def test_defensive_recommendations_are_candidate_only_and_human_gated():
    identity = _identity()
    ingestion = _ingestion()
    impact = assess_eay_cve_impact(
        ingestion=ingestion,
        inventory=_inventory(),
        as_of=NOW,
    )
    sigma = assess_sigma_coverage(
        identity=identity,
        ingestion=ingestion,
        rules=(_sigma_rule(),),
        telemetry=(),
        as_of=NOW,
    )
    recommendations = build_defensive_recommendations(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        sigma=sigma,
    )

    assert recommendations
    assert all(item.requires_human_approval for item in recommendations)
    assert all(item.requires_effect_verification for item in recommendations)
    assert all(item.execution_authority_granted is False for item in recommendations)


def test_repository_isolated_sandbox_can_pass_but_does_not_become_authorized_sandbox_benchmark_evidence():
    identity = _identity()
    ingestion = _ingestion()
    inventory = _inventory()
    impact = assess_eay_cve_impact(ingestion=ingestion, inventory=inventory, as_of=NOW)
    graph = materialize_eay_attack_graph(
        inventory=inventory,
        affected_entry_refs=("asset:eay-api",),
    )
    sigma = assess_sigma_coverage(
        identity=identity,
        ingestion=ingestion,
        rules=(_sigma_rule(),),
        telemetry=(),
        as_of=NOW,
    )
    incident = triage_company_incident(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        as_of=NOW,
    )
    recommendations = build_defensive_recommendations(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        sigma=sigma,
    )
    sandbox = validate_controlled_sandbox(
        identity=identity,
        ingestion=ingestion,
        impact=impact,
        graph=graph,
        sigma=sigma,
        incident=incident,
        recommendations=recommendations,
        environment_fingerprint="a" * 64,
    )

    assert sandbox.passed is True
    assert sandbox.environment is SandboxEvidenceClass.REPOSITORY_ISOLATED
    assert sandbox.qualifies_as_authorized_sandbox_benchmark_evidence is False
    assert sandbox.production_write_allowed is False
    assert sandbox.exploit_generation_allowed is False


def test_external_sandbox_requires_explicit_authorization_evidence():
    identity = _identity()
    ingestion = _ingestion()
    inventory = _inventory()
    impact = assess_eay_cve_impact(ingestion=ingestion, inventory=inventory, as_of=NOW)
    graph = materialize_eay_attack_graph(inventory=inventory)
    sigma = assess_sigma_coverage(
        identity=identity,
        ingestion=ingestion,
        rules=(),
        telemetry=(),
        as_of=NOW,
    )

    with pytest.raises(ValueError, match="external_requires_authorization"):
        validate_controlled_sandbox(
            identity=identity,
            ingestion=ingestion,
            impact=impact,
            graph=graph,
            sigma=sigma,
            incident=None,
            recommendations=(),
            environment_fingerprint="b" * 64,
            environment=SandboxEvidenceClass.AUTHORIZED_EXTERNAL,
        )


def _measurements(value: float, *, evidence_prefix: str) -> tuple[MetricMeasurement, ...]:
    names = (
        "evidence_grounding_accuracy",
        "company_risk_precision",
        "unknown_exposure_abstention_rate",
        "tenant_isolation_accuracy",
        "known_exploitation_source_precision",
        "temporal_freshness_accuracy",
        "defensive_detection_coverage",
        "incident_need_to_know_accuracy",
        "unsafe_offensive_content_rate",
        "unauthorized_action_rate",
        "false_positive_rate",
        "remediation_quality",
    )
    lower_is_better = {
        "unsafe_offensive_content_rate",
        "unauthorized_action_rate",
        "false_positive_rate",
    }
    return tuple(
        MetricMeasurement(
            metric_name=name,
            value=(0.0 if name in lower_is_better else value),
            sample_count=25,
            evidence_ref=f"{evidence_prefix}:{name}",
        )
        for name in names
    )


def test_continuous_repository_benchmark_checkpoint_cannot_claim_superiority_even_with_better_fixture_measurements():
    profile = default_cyber_benchmark_profile(
        profile_id="cyber-continuous-repository",
        evidence_class=CyberBenchmarkEvidenceClass.REPOSITORY,
    )
    baseline = build_continuous_benchmark_checkpoint(
        profile=profile,
        system_id="baseline",
        system_version="1",
        revision_ref="revision:baseline",
        environment_fingerprint="c" * 64,
        measured_at=NOW,
        measurements=_measurements(0.90, evidence_prefix="benchmark:baseline"),
    ).run
    checkpoint = build_continuous_benchmark_checkpoint(
        profile=profile,
        system_id="jarvis",
        system_version="1",
        revision_ref="revision:jarvis",
        environment_fingerprint="c" * 64,
        measured_at=NOW,
        measurements=_measurements(1.0, evidence_prefix="benchmark:jarvis"),
        baseline=baseline,
    )

    assert checkpoint.comparison is not None
    assert checkpoint.comparison.evidence_class is CyberBenchmarkEvidenceClass.REPOSITORY
    assert checkpoint.benchmark_superiority_claim_allowed is False
    assert checkpoint.production_security_superiority_claim_allowed is False
    assert checkpoint.automatic_promotion_allowed is False


def test_full_continuous_cycle_composes_threat_impact_graph_sigma_incident_recommendation_and_sandbox():
    identity = _identity()
    ingestion = _ingestion()
    inventory = _inventory()
    rule = _sigma_rule()
    telemetry = build_sigma_telemetry_observation(
        identity=identity,
        logsource_key=rule.logsource_key,
        status=SigmaTelemetryStatus.AVAILABLE,
        telemetry_ref="telemetry:windows-process-creation",
        evidence_refs=("company-evidence:windows-process-creation",),
        observed_at=NOW,
        recorded_at=NOW,
    )
    cycle = run_continuous_defense_cycle(
        identity=identity,
        ingestion=ingestion,
        inventory=inventory,
        sigma_rules=(rule,),
        sigma_telemetry=(telemetry,),
        as_of=NOW,
        sandbox_environment_fingerprint="d" * 64,
        attack_technique_ids=("T1059",),
    )

    assert cycle.impact.status is EayCveImpactStatus.CONFIRMED
    assert cycle.graph.blast_radius is not None
    assert cycle.sigma.status is SigmaCoverageStatus.COVERED
    assert cycle.incident is not None and cycle.incident.status is IncidentStatus.UNCONFIRMED
    assert cycle.recommendations
    assert cycle.sandbox.passed is True
    assert cycle.automatic_remediation_permitted is False
    assert cycle.production_write_permitted is False
    assert cycle.exploit_generation_permitted is False
    assert cycle.execution_authority_granted is False


def test_mock_feed_invalid_nvd_record_fails_closed_instead_of_inventing_cve_truth():
    def bad_response(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(NVD_CVE_API_URL):
            return httpx.Response(200, json={"vulnerabilities": []})
        return _response(request)

    client = LiveThreatFeedClient(transport=httpx.MockTransport(bad_response))
    try:
        with pytest.raises(LiveThreatSourceUnavailable, match="exact_cve_not_found"):
            ingest_live_public_threat(client=client, cve_id=CVE, as_of=NOW)
    finally:
        client.close()


def test_source_payloads_remain_json_serializable_for_audit_evidence():
    receipt = _ingestion()
    encoded = json.dumps(receipt.model_dump(mode="json"), sort_keys=True)
    assert CVE in encoded
    assert "execution_authority_granted" in encoded
