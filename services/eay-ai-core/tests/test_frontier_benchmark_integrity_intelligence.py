from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.frontier3_certification_intelligence import (
    BenchmarkProtocolIdentity,
    BenchmarkScenarioCoverage,
    Frontier3CertificationPolicy,
    FrontierCertificationDomain,
    FrontierSystemMeasurement,
    JarvisDomainMeasurement,
    certify_frontier3_matrix,
)
from app.frontier_benchmark_integrity_intelligence import (
    BenchmarkExposureMode,
    BenchmarkIntegrityPolicy,
    CurrentBenchmarkProtocol,
    CurrentFrontierRelease,
    FrontierBenchmarkIntegrityArtifact,
    FrontierBenchmarkValidity,
    MeasurementIntegrityAudit,
    assess_frontier_benchmark_integrity,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
CHECKED = NOW + timedelta(days=1)
DOMAIN = FrontierCertificationDomain.GENERAL_REASONING
VERSION = "jarvis-v-next"


def protocol(*, version: str = "v1", task_fingerprint: str = "a" * 64) -> BenchmarkProtocolIdentity:
    return BenchmarkProtocolIdentity(
        protocol_id="frontier3-general-reasoning",
        protocol_version=version,
        task_set_id="taskset-general-reasoning",
        task_set_fingerprint=task_fingerprint,
        environment_fingerprint="b" * 64,
        metric_set_fingerprint="c" * 64,
    )


def coverage() -> BenchmarkScenarioCoverage:
    return BenchmarkScenarioCoverage(
        holdout=True,
        out_of_distribution=True,
        adversarial=True,
        temporal=True,
    )


def jarvis(*, score: float = 0.96, measured_at: datetime | None = None) -> JarvisDomainMeasurement:
    return JarvisDomainMeasurement(
        measurement_id="jarvis-general",
        domain=DOMAIN,
        system_version=VERSION,
        normalized_score=score,
        confidence_lower=max(0.0, score - 0.02),
        confidence_upper=min(1.0, score + 0.02),
        confidence_level=0.95,
        sample_count=240,
        measured_at=measured_at or NOW - timedelta(days=1),
        protocol=protocol(),
        scenario_coverage=coverage(),
        independent_evaluator_ref="eval-jarvis",
        evidence_refs=("benchmark://jarvis/run", "benchmark://jarvis/review"),
        critical_safety_regression=False,
    )


def peers(*, measured_at: datetime | None = None) -> tuple[FrontierSystemMeasurement, ...]:
    measured = measured_at or NOW - timedelta(days=1)
    data = (
        ("frontier-a", "provider-a", 0.91, 0.89, 0.93),
        ("frontier-b", "provider-b", 0.93, 0.91, 0.95),
        ("frontier-c", "provider-c", 0.95, 0.93, 0.97),
    )
    return tuple(
        FrontierSystemMeasurement(
            measurement_id=f"peer-{idx}",
            domain=DOMAIN,
            system_id=system,
            system_version=f"{system}-2026-08",
            provider_family=provider,
            normalized_score=score,
            confidence_lower=lower,
            confidence_upper=upper,
            confidence_level=0.95,
            sample_count=240,
            measured_at=measured,
            protocol=protocol(),
            scenario_coverage=coverage(),
            independent_evaluator_ref=f"eval-peer-{idx}",
            frontier_qualification_evidence_ref=f"frontier://qualification/{system}",
            evidence_refs=(f"benchmark://{system}/run", f"benchmark://{system}/review"),
            frontier_qualified=True,
        )
        for idx, (system, provider, score, lower, upper) in enumerate(data, start=1)
    )


def cert_policy() -> Frontier3CertificationPolicy:
    return Frontier3CertificationPolicy(required_domains=(DOMAIN,))


def source_cert(
    *,
    jarvis_measurement: JarvisDomainMeasurement | None = None,
    peer_measurements: tuple[FrontierSystemMeasurement, ...] | None = None,
):
    return certify_frontier3_matrix(
        certification_id="frontier-cert-1",
        tenant_id="tenant-a",
        company_id="company-a",
        jarvis_system_id="jarvis",
        jarvis_system_version=VERSION,
        assessed_at=NOW,
        jarvis_measurements=(jarvis_measurement or jarvis(),),
        frontier_measurements=peer_measurements or peers(),
        policy=cert_policy(),
    )


def audits(
    measurements: tuple[JarvisDomainMeasurement | FrontierSystemMeasurement, ...],
    *,
    target: str | None = None,
    exposure: BenchmarkExposureMode = BenchmarkExposureMode.SECRET_HOLDOUT,
    contamination: bool = False,
    leakage: bool = False,
    unseen: float = 0.80,
    overlap: float = 0.01,
    future: bool = False,
) -> tuple[MeasurementIntegrityAudit, ...]:
    items: list[MeasurementIntegrityAudit] = []
    for measurement in measurements:
        for index in (1, 2):
            selected = measurement.measurement_id == target
            items.append(
                MeasurementIntegrityAudit(
                    audit_id=f"audit-{measurement.measurement_id}-{index}",
                    measurement_id=measurement.measurement_id,
                    auditor_ref=f"integrity-auditor-{measurement.measurement_id}-{index}",
                    independent_auditor=True,
                    audited_at=(CHECKED + timedelta(minutes=1)) if (future and selected and index == 1) else CHECKED,
                    exposure_mode=exposure if selected else BenchmarkExposureMode.SECRET_HOLDOUT,
                    rotation_id=(f"rotation-{measurement.measurement_id}" if selected and exposure is BenchmarkExposureMode.ROTATED_HOLDOUT else None),
                    unseen_item_fraction=unseen if selected else 0.80,
                    known_public_overlap_fraction=overlap if selected else 0.01,
                    prompt_answer_leakage_detected=leakage if selected else False,
                    contamination_detected=contamination if selected else False,
                    evidence_refs=(
                        f"integrity://{measurement.measurement_id}/{index}/scan",
                        f"integrity://{measurement.measurement_id}/{index}/review",
                    ),
                )
            )
    return tuple(items)


def releases(peer_measurements: tuple[FrontierSystemMeasurement, ...], *, newer_provider: str | None = None) -> tuple[CurrentFrontierRelease, ...]:
    values = []
    for peer in peer_measurements:
        changed = peer.provider_family == newer_provider
        values.append(
            CurrentFrontierRelease(
                provider_family=peer.provider_family,
                system_id=(f"{peer.system_id}-next" if changed else peer.system_id),
                system_version=(f"{peer.system_version}-next" if changed else peer.system_version),
                released_at=(NOW + timedelta(hours=12) if changed else NOW - timedelta(days=10)),
                benchmark_eligible=True,
                evidence_ref=f"release://{peer.provider_family}/current",
            )
        )
    return tuple(values)


def current_protocol(*, rotated: bool = False) -> tuple[CurrentBenchmarkProtocol, ...]:
    return (
        CurrentBenchmarkProtocol(
            domain=DOMAIN,
            protocol=(protocol(version="v2", task_fingerprint="d" * 64) if rotated else protocol()),
            effective_at=(NOW + timedelta(hours=12) if rotated else NOW - timedelta(days=10)),
            evidence_ref="protocol://general-reasoning/current",
        ),
    )


def assess(
    *,
    source=None,
    j: JarvisDomainMeasurement | None = None,
    p: tuple[FrontierSystemMeasurement, ...] | None = None,
    audit_values: tuple[MeasurementIntegrityAudit, ...] | None = None,
    release_values: tuple[CurrentFrontierRelease, ...] | None = None,
    protocol_values: tuple[CurrentBenchmarkProtocol, ...] | None = None,
    checked_at: datetime = CHECKED,
    current_version: str = VERSION,
):
    j = j or jarvis()
    p = p or peers()
    source = source or source_cert(jarvis_measurement=j, peer_measurements=p)
    measurements = (j, *p)
    return assess_frontier_benchmark_integrity(
        source=source,
        tenant_id="tenant-a",
        company_id="company-a",
        checked_at=checked_at,
        current_jarvis_system_version=current_version,
        jarvis_measurements=(j,),
        frontier_measurements=p,
        audits=audit_values or audits(measurements),
        current_frontier_releases=release_values or releases(p),
        current_protocols=protocol_values or current_protocol(),
        certification_policy=cert_policy(),
    )


def test_clean_hidden_audits_and_current_frontier_preserve_bounded_certificate() -> None:
    result = assess()
    assert result.validity is FrontierBenchmarkValidity.VALID
    assert result.bounded_matrix_parity_claim_still_valid is True
    assert result.bounded_matrix_superiority_claim_still_valid is False
    assert result.audited_measurement_count == 4
    assert result.frontier_release_count == 3
    assert result.current_protocol_count == 1
    assert result.universal_superiority_claim_allowed is False
    assert result.execution_authority_granted is False


def test_confirmed_contamination_or_prompt_answer_leakage_revokes_claim() -> None:
    j = jarvis()
    p = peers()
    contaminated = assess(j=j, p=p, audit_values=audits((j, *p), target="jarvis-general", contamination=True))
    assert contaminated.validity is FrontierBenchmarkValidity.REVOKED
    assert "frontier_integrity_contamination_detected:jarvis-general" in contaminated.blockers
    assert contaminated.bounded_matrix_parity_claim_still_valid is False

    leaked = assess(j=j, p=p, audit_values=audits((j, *p), target="peer-2", leakage=True))
    assert leaked.validity is FrontierBenchmarkValidity.REVOKED
    assert "frontier_integrity_prompt_answer_leakage:peer-2" in leaked.blockers


def test_public_static_eval_without_hidden_rotation_is_not_admissible() -> None:
    j = jarvis()
    p = peers()
    result = assess(
        j=j,
        p=p,
        audit_values=audits((j, *p), target="peer-1", exposure=BenchmarkExposureMode.PUBLIC_STATIC),
    )
    assert result.validity is FrontierBenchmarkValidity.HOLD
    assert "frontier_integrity_public_static_eval_not_admissible:peer-1" in result.blockers


def test_unseen_fraction_and_public_overlap_are_hard_integrity_gates() -> None:
    j = jarvis()
    p = peers()
    weak_unseen = assess(j=j, p=p, audit_values=audits((j, *p), target="peer-3", unseen=0.10))
    assert "frontier_integrity_unseen_fraction_insufficient:peer-3" in weak_unseen.blockers

    overlap = assess(j=j, p=p, audit_values=audits((j, *p), target="peer-3", overlap=0.20))
    assert "frontier_integrity_public_overlap_excessive:peer-3" in overlap.blockers


def test_two_independent_auditors_distinct_from_benchmark_evaluator_are_required() -> None:
    j = jarvis()
    p = peers()
    values = list(audits((j, *p)))
    values = [item for item in values if not (item.measurement_id == "peer-1" and item.audit_id.endswith("-2"))]
    result = assess(j=j, p=p, audit_values=tuple(values))
    assert "frontier_integrity_auditor_quorum_missing:peer-1" in result.blockers

    values = list(audits((j, *p)))
    values[2] = values[2].model_copy(update={"auditor_ref": "eval-peer-1"})
    result = assess(j=j, p=p, audit_values=tuple(values))
    assert "frontier_integrity_auditor_quorum_missing:peer-1" in result.blockers


def test_new_benchmark_eligible_frontier_release_invalidates_old_comparison_immediately() -> None:
    j = jarvis()
    p = peers()
    result = assess(j=j, p=p, release_values=releases(p, newer_provider="provider-c"))
    assert result.validity is FrontierBenchmarkValidity.HOLD
    assert "frontier_integrity_newer_frontier_release_requires_rebenchmark:provider-c" in result.blockers
    assert result.bounded_matrix_parity_claim_still_valid is False


def test_jarvis_version_drift_requires_rebenchmark_instead_of_inheriting_old_score() -> None:
    result = assess(current_version="jarvis-v-next-plus-one")
    assert result.validity is FrontierBenchmarkValidity.HOLD
    assert "frontier_integrity_jarvis_version_drift" in result.blockers


def test_protocol_rotation_requires_rebenchmark() -> None:
    result = assess(protocol_values=current_protocol(rotated=True))
    assert result.validity is FrontierBenchmarkValidity.HOLD
    assert "frontier_integrity_protocol_rotated_requires_rebenchmark:general_reasoning" in result.blockers


def test_certificate_measurements_age_out_relative_to_current_check_time() -> None:
    old_measurement_time = NOW - timedelta(days=1)
    j = jarvis(measured_at=old_measurement_time)
    p = peers(measured_at=old_measurement_time)
    source = source_cert(jarvis_measurement=j, peer_measurements=p)
    late_check = NOW + timedelta(days=31)
    result = assess(
        source=source,
        j=j,
        p=p,
        audit_values=audits((j, *p)),
        checked_at=late_check,
        release_values=releases(p),
        protocol_values=current_protocol(),
    )
    assert result.validity is FrontierBenchmarkValidity.HOLD
    assert any(code.startswith("frontier_integrity_measurement_now_stale:") for code in result.blockers)


def test_future_audit_release_or_protocol_evidence_fails_closed() -> None:
    j = jarvis()
    p = peers()
    future_audit = assess(j=j, p=p, audit_values=audits((j, *p), target="peer-2", future=True))
    assert "frontier_integrity_future_audit_forbidden:peer-2" in future_audit.blockers

    current = list(releases(p))
    current[0] = current[0].model_copy(update={"released_at": CHECKED + timedelta(minutes=1)})
    future_release = assess(j=j, p=p, release_values=tuple(current))
    assert "frontier_integrity_future_release_forbidden:provider-a" in future_release.blockers

    future_protocol = (
        CurrentBenchmarkProtocol(
            domain=DOMAIN,
            protocol=protocol(),
            effective_at=CHECKED + timedelta(minutes=1),
            evidence_ref="protocol://future",
        ),
    )
    result = assess(j=j, p=p, protocol_values=future_protocol)
    assert "frontier_integrity_future_protocol_forbidden:general_reasoning" in result.blockers


def test_raw_measurements_must_reproduce_the_sealed_source_certificate() -> None:
    j = jarvis()
    p = peers()
    source = source_cert(jarvis_measurement=j, peer_measurements=p)
    changed = jarvis(score=0.97)
    with pytest.raises(ValueError, match="frontier_integrity_recertification_mismatch"):
        assess(source=source, j=changed, p=p, audit_values=audits((changed, *p)))


def test_audits_cannot_reference_unknown_measurements_and_source_is_scope_bound() -> None:
    j = jarvis()
    p = peers()
    unknown = list(audits((j, *p)))
    unknown[0] = unknown[0].model_copy(update={"measurement_id": "unknown-measurement"})
    with pytest.raises(ValueError, match="frontier_integrity_audit_references_unknown_measurement"):
        assess(j=j, p=p, audit_values=tuple(unknown))

    source = source_cert(jarvis_measurement=j, peer_measurements=p)
    with pytest.raises(ValueError, match="frontier_integrity_cross_tenant_source_forbidden"):
        assess_frontier_benchmark_integrity(
            source=source,
            tenant_id="tenant-b",
            company_id="company-a",
            checked_at=CHECKED,
            current_jarvis_system_version=VERSION,
            jarvis_measurements=(j,),
            frontier_measurements=p,
            audits=audits((j, *p)),
            current_frontier_releases=releases(p),
            current_protocols=current_protocol(),
            certification_policy=cert_policy(),
        )


def test_integrity_policy_cannot_disable_hidden_or_rotated_eval_gate() -> None:
    with pytest.raises(ValueError, match="frontier_integrity_hidden_or_rotated_eval_cannot_be_disabled"):
        BenchmarkIntegrityPolicy(require_hidden_or_rotated_eval=False)


def test_integrity_artifact_tampering_and_authority_escalation_are_rejected() -> None:
    result = assess()
    tampered = result.model_copy(update={"audited_measurement_count": 0})
    with pytest.raises(ValueError, match="frontier_integrity_fingerprint_mismatch"):
        FrontierBenchmarkIntegrityArtifact.model_validate(tampered.model_dump(mode="json"))

    escalated = result.model_copy(update={"automatic_training_allowed": True})
    with pytest.raises(ValueError, match="frontier_integrity_never_mints_change_or_execution_authority"):
        FrontierBenchmarkIntegrityArtifact.model_validate(escalated.model_dump(mode="json"))
