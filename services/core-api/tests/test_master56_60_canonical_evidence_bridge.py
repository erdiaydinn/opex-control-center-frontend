from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from app.acceptance.external_evidence import EvidenceRecord, load_requirements
from app.release.canonical_evidence_bridge import (
    CanonicalSreEvidence,
    build_canonical_external_refs,
    build_canonical_sre_refs,
)
from app.sre.chaos_dr import ChaosResult, DrResult, load_chaos_dr_contract
from app.sre.governance import AcceptanceEvidence, load_sre_registry
from app.sre.observability import TelemetryEvent, load_observability_contract

ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE = ROOT / "docs" / "governance"
TENANT = "pilot-tenant"
RELEASE = "eay-rc-1"
CANDIDATE = "a" * 40
NOW = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)


def _digest(value: object) -> str:
    return sha256(str(value).encode()).hexdigest()


def _telemetry_events() -> tuple[TelemetryEvent, ...]:
    contract = load_observability_contract(GOVERNANCE / "eay_observability_contract.json")
    return tuple(
        TelemetryEvent(
            signal=str(signal),
            service="platform-core",
            environment="managed-staging",
            workflow="release",
            operation="verify",
            result="ok",
            dimensions={"tenant_safe_hash": "tenant-safe"},
        )
        for signal in contract["required_signals"]
    )


def _scale_evidence() -> dict[str, AcceptanceEvidence]:
    registry = load_sre_registry(GOVERNANCE / "eay_sre_service_registry.json")
    evidence: dict[str, AcceptanceEvidence] = {}
    for profile in registry["production_shape_tests"]:
        key = str(profile["key"])
        required = str(profile["required_evidence"])
        evidence_class = (
            "REAL_MEDIA_ENVIRONMENT"
            if required == "REAL_MEDIA_ENVIRONMENT_LOAD"
            else "MANAGED_STAGING"
        )
        evidence[key] = AcceptanceEvidence(
            key,
            evidence_class,
            "managed-production-shape",
            True,
            f"load-report:{key}",
        )
    return evidence


def _chaos_results() -> tuple[ChaosResult, ...]:
    contract = load_chaos_dr_contract(GOVERNANCE / "eay_chaos_dr_acceptance.json")
    invariants = tuple(str(value) for value in contract["required_invariants"])
    return tuple(
        ChaosResult(
            scenario=str(scenario),
            environment="managed-staging",
            measured=True,
            passed_invariants=invariants,
            provenance=f"chaos-report:{scenario}",
        )
        for scenario in contract["chaos_scenarios"]
    )


def _dr_result() -> DrResult:
    return DrResult(
        environment="managed-staging",
        restore_passed=True,
        rpo_seconds=120,
        rto_seconds=300,
        provenance="restore-report:1",
    )


def _sre_evidence() -> CanonicalSreEvidence:
    return CanonicalSreEvidence(
        telemetry_events=_telemetry_events(),
        scale_evidence=_scale_evidence(),
        chaos_results=_chaos_results(),
        dr_result=_dr_result(),
        observability_artifact_sha256=_digest("observability"),
        scale_artifact_sha256=_digest("scale"),
        chaos_artifact_sha256=_digest("chaos"),
        dr_artifact_sha256=_digest("dr"),
    )


def _external_class(required: str) -> str:
    return {
        "REAL_ENVIRONMENT": "REAL_ENVIRONMENT",
        "MANAGED_STAGING_OR_REAL": "MANAGED_STAGING",
        "REAL_STAGING": "REAL_STAGING",
        "REAL_BUILD_UAT": "REAL_BUILD_UAT",
    }[required]


def _external_records() -> tuple[EvidenceRecord, ...]:
    requirements = load_requirements(
        GOVERNANCE / "eay_external_acceptance_requirements.json"
    )
    records: list[EvidenceRecord] = []
    for requirement in requirements["requirements"]:
        item = int(requirement["item"])
        for evidence_key in requirement["evidence"]:
            key = str(evidence_key)
            records.append(
                EvidenceRecord(
                    tenant_id=TENANT,
                    release_id=RELEASE,
                    candidate_sha=CANDIDATE,
                    requirement_key=str(requirement["key"]),
                    evidence_key=key,
                    evidence_class=_external_class(str(requirement["required_class"])),
                    status="PASS",
                    environment="governed-release-evidence",
                    provenance=f"evidence:{item}:{key}",
                    artifact_sha256=_digest(f"{item}:{key}"),
                    approver=f"owner:{item}",
                    observed_at=NOW - timedelta(hours=1),
                    expires_at=NOW + timedelta(days=7),
                )
            )
    return tuple(records)


def test_canonical_bridge_uses_full_version_controlled_45_55_contracts() -> None:
    sre_refs = build_canonical_sre_refs(ROOT, _sre_evidence())
    external_refs = build_canonical_external_refs(
        ROOT,
        _external_records(),
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW,
    )

    assert set(sre_refs) == set(range(45, 49))
    assert set(external_refs) == set(range(49, 56))
    assert all(value.startswith("sre-sha256:") for value in sre_refs.values())
    assert all(value.startswith("ledger-sha256:") for value in external_refs.values())


def test_incomplete_sre_input_cannot_mint_canonical_release_fingerprints() -> None:
    evidence = _sre_evidence()
    with pytest.raises(ValueError, match="every required signal"):
        build_canonical_sre_refs(
            ROOT,
            replace(evidence, telemetry_events=evidence.telemetry_events[:1]),
        )

    missing_scale = dict(evidence.scale_evidence)
    missing_scale.pop(next(iter(missing_scale)))
    with pytest.raises(ValueError, match="production-shape evidence failed"):
        build_canonical_sre_refs(
            ROOT,
            replace(evidence, scale_evidence=missing_scale),
        )

    with pytest.raises(ValueError, match="each governed scenario"):
        build_canonical_sre_refs(
            ROOT,
            replace(evidence, chaos_results=evidence.chaos_results[:-1]),
        )

    with pytest.raises(ValueError, match="DR evidence is not accepted"):
        build_canonical_sre_refs(
            ROOT,
            replace(evidence, dr_result=replace(evidence.dr_result, environment="ci")),
        )


def test_external_bridge_rechecks_expiry_against_canonical_matrix() -> None:
    records = _external_records()
    current = build_canonical_external_refs(
        ROOT,
        records,
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW,
    )
    expired = build_canonical_external_refs(
        ROOT,
        records,
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW + timedelta(days=8),
    )

    assert set(current) == set(range(49, 56))
    assert expired == {}


def test_external_bridge_rejects_synthetic_substitution() -> None:
    records = list(_external_records())
    first = records[0]
    records[0] = replace(
        first,
        evidence_class="SYNTHETIC",
        environment="ci",
        provenance="ci:synthetic",
    )
    refs = build_canonical_external_refs(
        ROOT,
        tuple(records),
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW,
    )

    assert 49 not in refs
    assert set(refs) == set(range(50, 56))
