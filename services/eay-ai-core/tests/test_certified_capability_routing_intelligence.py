from datetime import UTC, datetime, timedelta

import pytest

from app.certified_capability_routing_intelligence import (
    AdmissionDisposition, AdmissionStatus, CertifiedEngineCandidateAdmission,
    build_certified_capability_snapshot, seal_engine_capability_evidence,
)
from app.engine_gateway import EngineEndpoint, EngineProvider, RegisteredEngine
from app.frontier3_certification_intelligence import (
    BenchmarkProtocolIdentity, BenchmarkScenarioCoverage, Frontier3CertificationPolicy,
    FrontierCertificationDomain, FrontierSystemMeasurement, JarvisDomainMeasurement,
    certify_frontier3_matrix,
)
from app.frontier_benchmark_integrity_intelligence import (
    BenchmarkExposureMode, CurrentBenchmarkProtocol, CurrentFrontierRelease,
    MeasurementIntegrityAudit, assess_frontier_benchmark_integrity,
)
from app.intelligence_router import (
    EngineClass, IntelligenceEngine, IntelligenceTask, PrivacyLevel,
    TaskComplexity, TaskRisk,
)

NOW = datetime(2026, 8, 22, 12, tzinfo=UTC)
CHECKED = NOW + timedelta(days=1)
DOMAIN = FrontierCertificationDomain.GENERAL_REASONING
VERSION = "jarvis-v-next"


def protocol():
    return BenchmarkProtocolIdentity(protocol_id="p", protocol_version="v1", task_set_id="t",
        task_set_fingerprint="a"*64, environment_fingerprint="b"*64,
        metric_set_fingerprint="c"*64)


def coverage():
    return BenchmarkScenarioCoverage(holdout=True, out_of_distribution=True,
        adversarial=True, temporal=True)


def measurements():
    j = JarvisDomainMeasurement(measurement_id="jarvis-general", domain=DOMAIN,
        system_version=VERSION, normalized_score=.96, confidence_lower=.94,
        confidence_upper=.98, sample_count=240, measured_at=NOW-timedelta(days=1),
        protocol=protocol(), scenario_coverage=coverage(), independent_evaluator_ref="eval-j",
        evidence_refs=("bench://j/run", "bench://j/review"))
    peers = tuple(FrontierSystemMeasurement(measurement_id=f"peer-{i}", domain=DOMAIN,
        system_id=f"frontier-{i}", system_version=f"v{i}", provider_family=f"provider-{i}",
        normalized_score=score, confidence_lower=score-.02, confidence_upper=score+.02,
        sample_count=240, measured_at=NOW-timedelta(days=1), protocol=protocol(),
        scenario_coverage=coverage(), independent_evaluator_ref=f"eval-p{i}",
        frontier_qualification_evidence_ref=f"frontier://q/{i}",
        evidence_refs=(f"bench://p{i}/run", f"bench://p{i}/review"), frontier_qualified=True)
        for i, score in enumerate((.91, .93, .95), 1))
    return j, peers


def source_and_integrity():
    j, peers = measurements()
    policy = Frontier3CertificationPolicy(required_domains=(DOMAIN,))
    source = certify_frontier3_matrix(certification_id="cert-1", tenant_id="tenant-a",
        company_id="company-a", jarvis_system_id="jarvis", jarvis_system_version=VERSION,
        assessed_at=NOW, jarvis_measurements=(j,), frontier_measurements=peers, policy=policy)
    all_measurements = (j, *peers)
    audits = tuple(MeasurementIntegrityAudit(audit_id=f"audit-{m.measurement_id}-{n}",
        measurement_id=m.measurement_id, auditor_ref=f"auditor-{m.measurement_id}-{n}",
        independent_auditor=True, audited_at=CHECKED,
        exposure_mode=BenchmarkExposureMode.SECRET_HOLDOUT, unseen_item_fraction=.8,
        known_public_overlap_fraction=.01,
        evidence_refs=(f"integrity://{m.measurement_id}/{n}/scan",
                       f"integrity://{m.measurement_id}/{n}/review"))
        for m in all_measurements for n in (1, 2))
    releases = tuple(CurrentFrontierRelease(provider_family=p.provider_family,
        system_id=p.system_id, system_version=p.system_version,
        released_at=NOW-timedelta(days=10), benchmark_eligible=True,
        evidence_ref=f"release://{p.provider_family}") for p in peers)
    current = (CurrentBenchmarkProtocol(domain=DOMAIN, protocol=protocol(),
        effective_at=NOW-timedelta(days=10), evidence_ref="protocol://current"),)
    integrity = assess_frontier_benchmark_integrity(source=source, tenant_id="tenant-a",
        company_id="company-a", checked_at=CHECKED, current_jarvis_system_version=VERSION,
        jarvis_measurements=(j,), frontier_measurements=peers, audits=audits,
        current_frontier_releases=releases, current_protocols=current,
        certification_policy=policy)
    return source, integrity


def evidence(source, integrity, *, score=.96, contamination=False, company="company-a"):
    return seal_engine_capability_evidence(evidence_id="engine-evidence-1", tenant_id="tenant-a",
        company_id=company, domain=DOMAIN, engine_id="engine-a", model_id="model-a",
        provider_family="provider-a", normalized_score=score, sample_count=240,
        measured_at=CHECKED-timedelta(hours=1), scenario_coverage=coverage(),
        independent_evaluator_refs=("eval-x", "eval-y"), exact_adapter_verified=True,
        contamination_detected=contamination,
        source_certification_fingerprint=source.fingerprint,
        source_integrity_fingerprint=integrity.fingerprint,
        evidence_refs=("cap://run", "cap://review"))


def registration():
    return RegisteredEngine(profile=IntelligenceEngine(engine_id="engine-a",
        engine_class=EngineClass.FRONTIER, production_enabled=True, exact_adapter_verified=True,
        maximum_privacy=PrivacyLevel.PUBLIC, maximum_risk=TaskRisk.CRITICAL,
        benchmark_score=1.0, benchmark_evidence_ref="legacy://score",
        independent_provider_key="provider-a"),
        endpoint=EngineEndpoint(engine_id="engine-a", provider=EngineProvider.OPENAI_RESPONSES,
        model_id="model-a", base_url="https://api.openai.com", secret_ref="env:OPENAI_API_KEY"))


def task():
    return IntelligenceTask(task_id="t1", complexity=TaskComplexity.HARD, risk=TaskRisk.HIGH,
        privacy=PrivacyLevel.PUBLIC, certification_domain=DOMAIN,
        requires_fresh_certification=True)


def test_valid_frontier_evidence_creates_exact_runtime_admission():
    source, integrity = source_and_integrity()
    snap = build_certified_capability_snapshot(source=source, integrity=integrity,
        checked_at=CHECKED, engine_evidence=(evidence(source, integrity),))
    assert snap.disposition is AdmissionDisposition.READY
    assert snap.admissions[0].status is AdmissionStatus.ADMITTED
    gate = CertifiedEngineCandidateAdmission(snap)
    assert gate.is_admitted(task=task(), registration=registration(), requested_at=CHECKED,
        tenant_ref="tenant-a", company_ref="company-a")


def test_engine_below_strongest_frontier_fails_closed():
    source, integrity = source_and_integrity()
    snap = build_certified_capability_snapshot(source=source, integrity=integrity,
        checked_at=CHECKED, engine_evidence=(evidence(source, integrity, score=.94),))
    assert snap.disposition is AdmissionDisposition.HOLD
    assert snap.admissions[0].status is AdmissionStatus.BELOW_FRONTIER


def test_engine_contamination_revokes_runtime_candidate():
    source, integrity = source_and_integrity()
    snap = build_certified_capability_snapshot(source=source, integrity=integrity,
        checked_at=CHECKED, engine_evidence=(evidence(source, integrity, contamination=True),))
    assert snap.admissions[0].status is AdmissionStatus.REVOKED
    assert snap.disposition is AdmissionDisposition.HOLD


def test_scope_and_tamper_are_rejected():
    source, integrity = source_and_integrity()
    with pytest.raises(ValueError, match="cross_scope"):
        build_certified_capability_snapshot(source=source, integrity=integrity, checked_at=CHECKED,
            engine_evidence=(evidence(source, integrity, company="company-b"),))
    original = evidence(source, integrity)
    tampered = original.model_copy(update={"normalized_score": 1.0})
    with pytest.raises(ValueError, match="fingerprint"):
        build_certified_capability_snapshot(source=source, integrity=integrity, checked_at=CHECKED,
            engine_evidence=(tampered,))


def test_admission_is_exact_company_domain_model_provider_and_time_bound():
    source, integrity = source_and_integrity()
    snap = build_certified_capability_snapshot(source=source, integrity=integrity,
        checked_at=CHECKED, engine_evidence=(evidence(source, integrity),))
    gate = CertifiedEngineCandidateAdmission(snap)
    assert not gate.is_admitted(task=task(), registration=registration(), requested_at=CHECKED,
        tenant_ref="tenant-a", company_ref="company-b")
    wrong = registration().model_copy(update={"endpoint": registration().endpoint.model_copy(update={"model_id": "model-b"})})
    assert not gate.is_admitted(task=task(), registration=wrong, requested_at=CHECKED,
        tenant_ref="tenant-a", company_ref="company-a")
    assert gate.receipt_ref(task=task(), requested_at=snap.valid_until+timedelta(seconds=1),
        tenant_ref="tenant-a", company_ref="company-a") is None
