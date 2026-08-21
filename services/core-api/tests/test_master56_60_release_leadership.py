from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from app.acceptance.external_evidence import (
    EvidenceRecord,
    build_external_item_refs,
    load_requirements,
)
from app.release.category_leadership import (
    PILOT_METRICS,
    PROD_SIGNOFFS,
    REQUIRED_EXTERNAL,
    REQUIRED_SRE,
    STABILIZATION_METRICS,
    BenchmarkSignal,
    ReleaseScope,
    ReleaseState,
    ReleaseTruth,
    StabilizationIssue,
    bind_authority_ref,
    bind_release_evidence_ref,
    build_chaos_item_ref,
    build_dr_item_ref,
    build_observability_item_ref,
    build_scale_item_ref,
    category_leadership_backlog,
    next_state,
    stabilization_backlog,
)
from app.sre.chaos_dr import ChaosResult, DrResult
from app.sre.governance import AcceptanceEvidence
from app.sre.observability import TelemetryEvent

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_REQUIREMENTS = ROOT / "docs/governance/eay_external_acceptance_requirements.json"
CANDIDATE = "a" * 40
TENANT = "pilot-tenant"
RELEASE = "eay-rc-1"
NOW = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)
CHAOS_SCENARIOS = tuple(f"scenario-{index}" for index in range(1, 15))


def _artifact(value: object) -> str:
    return sha256(str(value).encode()).hexdigest()


def _raw_ref(prefix: str, value: object) -> str:
    return f"{prefix}-sha256:{_artifact(value)}"


def _bound_ref(prefix: str, value: object) -> str:
    return bind_release_evidence_ref(
        prefix,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        artifact_sha256=_artifact(value),
    )


def _observability_contract() -> dict[str, object]:
    return {
        "required_signals": ["logs", "traces"],
        "required_dimensions": [
            "service",
            "tenant_safe_hash",
            "environment",
            "workflow",
            "operation",
            "result",
        ],
        "forbidden_dimensions": ["raw_secret"],
    }


def _telemetry_events() -> tuple[TelemetryEvent, ...]:
    return tuple(
        TelemetryEvent(
            signal=signal,
            service="platform-core",
            environment="managed-staging",
            workflow="release",
            operation="verify",
            result="ok",
            dimensions={"tenant_safe_hash": "tenant-safe"},
        )
        for signal in ("logs", "traces")
    )


def _scale_registry() -> dict[str, object]:
    return {
        "production_shape_tests": [
            {
                "key": "portal_3000_users",
                "required_evidence": "MANAGED_STAGING_LOAD",
            },
            {
                "key": "academy_1200_media_concurrency",
                "required_evidence": "REAL_MEDIA_ENVIRONMENT_LOAD",
            },
        ]
    }


def _scale_evidence() -> dict[str, AcceptanceEvidence]:
    return {
        "portal_3000_users": AcceptanceEvidence(
            "portal_3000_users",
            "MANAGED_STAGING",
            "managed-staging",
            True,
            "load-report:portal",
        ),
        "academy_1200_media_concurrency": AcceptanceEvidence(
            "academy_1200_media_concurrency",
            "REAL_MEDIA_ENVIRONMENT",
            "media-production-shape",
            True,
            "load-report:academy",
        ),
    }


def _chaos_contract() -> dict[str, object]:
    return {
        "chaos_scenarios": list(CHAOS_SCENARIOS),
        "required_invariants": ["tenant_isolation", "idempotency"],
    }


def _chaos_results() -> tuple[ChaosResult, ...]:
    return tuple(
        ChaosResult(
            scenario,
            "managed-staging",
            True,
            ("tenant_isolation", "idempotency"),
            f"chaos-run:{scenario}",
        )
        for scenario in CHAOS_SCENARIOS
    )


def _dr_result() -> DrResult:
    return DrResult(
        environment="managed-staging",
        restore_passed=True,
        rpo_seconds=120,
        rto_seconds=300,
        provenance="restore-report:1",
    )


def _raw_sre_refs() -> dict[int, str]:
    return {
        45: build_observability_item_ref(
            _observability_contract(),
            _telemetry_events(),
            artifact_sha256=_artifact("observability-report"),
        ),
        46: build_scale_item_ref(
            _scale_registry(),
            _scale_evidence(),
            artifact_sha256=_artifact("load-report"),
        ),
        47: build_chaos_item_ref(
            _chaos_contract(),
            _chaos_results(),
            artifact_sha256=_artifact("chaos-report"),
        ),
        48: build_dr_item_ref(
            _dr_result(),
            artifact_sha256=_artifact("dr-report"),
        ),
    }


def _external_class(required: str) -> str:
    mapping = {
        "REAL_ENVIRONMENT": "REAL_ENVIRONMENT",
        "MANAGED_STAGING_OR_REAL": "MANAGED_STAGING",
        "REAL_STAGING": "REAL_STAGING",
        "REAL_BUILD_UAT": "REAL_BUILD_UAT",
    }
    return mapping[required]


def _external_requirements() -> dict[str, object]:
    return load_requirements(EXTERNAL_REQUIREMENTS)


def _external_records() -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for requirement in _external_requirements()["requirements"]:
        item = int(requirement["item"])
        evidence_class = _external_class(str(requirement["required_class"]))
        for key in requirement["evidence"]:
            evidence_key = str(key)
            records.append(
                EvidenceRecord(
                    tenant_id=TENANT,
                    release_id=RELEASE,
                    candidate_sha=CANDIDATE,
                    requirement_key=str(requirement["key"]),
                    evidence_key=evidence_key,
                    evidence_class=evidence_class,
                    status="PASS",
                    environment="governed-release-evidence",
                    provenance=f"evidence:{item}:{evidence_key}",
                    artifact_sha256=_artifact(f"{item}:{evidence_key}"),
                    approver=f"owner:{item}",
                    observed_at=NOW - timedelta(hours=1),
                    expires_at=NOW + timedelta(days=7),
                )
            )
    return tuple(records)


def _raw_external_refs() -> dict[int, str]:
    return build_external_item_refs(
        _external_requirements(),
        _external_records(),
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW,
    )


def _bound_authority_refs(kind: str, refs: dict[int, str]) -> dict[int, str]:
    return {
        item: bind_authority_ref(
            kind,
            source_ref,
            release_id=RELEASE,
            candidate_sha=CANDIDATE,
        )
        for item, source_ref in refs.items()
    }


def full_truth() -> ReleaseTruth:
    pilot_scope = ReleaseScope(
        tenant_ids=(TENANT,),
        modules=("workforce", "inventory"),
        evidence_ref=_bound_ref("scope", "pilot"),
        owner="pilot-owner",
    )
    activation_scope = ReleaseScope(
        tenant_ids=(TENANT,),
        modules=("workforce", "inventory"),
        evidence_ref=_bound_ref("scope", "activation"),
        owner="release-owner",
    )
    return ReleaseTruth(
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        repository_green=True,
        repository_evidence_ref=f"github-status:{CANDIDATE}",
        sre_items={item: True for item in REQUIRED_SRE},
        sre_evidence_refs=_bound_authority_refs("sre", _raw_sre_refs()),
        external_items={item: True for item in REQUIRED_EXTERNAL},
        external_evidence_refs=_bound_authority_refs("ledger", _raw_external_refs()),
        pilot_scope=pilot_scope,
        pilot_plan_ref=_bound_ref("plan", "pilot-plan"),
        pilot_rollback_ref=_bound_ref("rollback", "pilot-rollback"),
        pilot_metrics={key: True for key in PILOT_METRICS},
        pilot_evidence_refs={key: _bound_ref("pilot", key) for key in PILOT_METRICS},
        activation_scope=activation_scope,
        activation_plan_ref=_bound_ref("plan", "activation-plan"),
        activation_rollback_ref=_bound_ref("rollback", "activation-rollback"),
        signoffs={key: True for key in PROD_SIGNOFFS},
        signoff_evidence_refs={key: _bound_ref("signoff", key) for key in PROD_SIGNOFFS},
        stabilization_metrics={key: True for key in STABILIZATION_METRICS},
        stabilization_evidence_refs={
            key: _bound_ref("stabilization", key) for key in STABILIZATION_METRICS
        },
    )


def test_canonical_45_55_bridges_produce_release_fingerprints() -> None:
    sre_refs = _raw_sre_refs()
    external_refs = _raw_external_refs()
    assert set(sre_refs) == set(REQUIRED_SRE)
    assert set(external_refs) == set(REQUIRED_EXTERNAL)
    assert all(value.startswith("sre-sha256:") for value in sre_refs.values())
    assert all(value.startswith("ledger-sha256:") for value in external_refs.values())

    bound_sre = _bound_authority_refs("sre", sre_refs)
    bound_external = _bound_authority_refs("ledger", external_refs)
    assert all(CANDIDATE in value for value in bound_sre.values())
    assert all(CANDIDATE in value for value in bound_external.values())


def test_canonical_sre_bridge_rejects_incomplete_or_synthetic_evidence() -> None:
    incomplete_events = _telemetry_events()[:1]
    with pytest.raises(ValueError, match="every required signal"):
        build_observability_item_ref(
            _observability_contract(),
            incomplete_events,
            artifact_sha256=_artifact("observability-report"),
        )

    synthetic_scale = dict(_scale_evidence())
    synthetic_scale["portal_3000_users"] = AcceptanceEvidence(
        "portal_3000_users",
        "SYNTHETIC",
        "ci",
        True,
        "ci:load",
    )
    with pytest.raises(ValueError, match="production-shape evidence failed"):
        build_scale_item_ref(
            _scale_registry(),
            synthetic_scale,
            artifact_sha256=_artifact("load-report"),
        )

    with pytest.raises(ValueError, match="each governed scenario"):
        build_chaos_item_ref(
            _chaos_contract(),
            _chaos_results()[:-1],
            artifact_sha256=_artifact("chaos-report"),
        )

    with pytest.raises(ValueError, match="DR evidence is not accepted"):
        build_dr_item_ref(
            replace(_dr_result(), environment="ci"),
            artifact_sha256=_artifact("dr-report"),
        )


def test_repository_green_alone_can_never_create_rc() -> None:
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.DEVELOPMENT,
            ReleaseTruth(
                release_id=RELEASE,
                candidate_sha=CANDIDATE,
                repository_green=True,
                repository_evidence_ref=f"github-status:{CANDIDATE}",
            ),
        )


def test_boolean_only_external_or_sre_truth_cannot_create_rc() -> None:
    truth = ReleaseTruth(
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        repository_green=True,
        repository_evidence_ref=f"github-status:{CANDIDATE}",
        sre_items={item: True for item in REQUIRED_SRE},
        external_items={item: True for item in REQUIRED_EXTERNAL},
    )
    with pytest.raises(ValueError):
        next_state(ReleaseState.DEVELOPMENT, truth)


def test_old_release_or_other_candidate_evidence_cannot_be_reused() -> None:
    truth = full_truth()
    stale_external = dict(truth.external_evidence_refs)
    stale_external[49] = bind_authority_ref(
        "ledger",
        _raw_external_refs()[49],
        release_id="old-release",
        candidate_sha=CANDIDATE,
    )
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.DEVELOPMENT,
            replace(truth, external_evidence_refs=stale_external),
        )

    other_candidate_signoffs = dict(truth.signoff_evidence_refs)
    other_candidate_signoffs["security"] = bind_release_evidence_ref(
        "signoff",
        release_id=RELEASE,
        candidate_sha="b" * 40,
        artifact_sha256=_artifact("security"),
    )
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            replace(truth, signoff_evidence_refs=other_candidate_signoffs),
            tenant_ids=(TENANT,),
            modules=("inventory",),
        )


def test_release_chain_requires_scoped_pilot_activation_and_stabilization() -> None:
    truth = full_truth()
    assert next_state(ReleaseState.DEVELOPMENT, truth) == ReleaseState.PRODUCTION_CANDIDATE
    assert next_state(ReleaseState.PRODUCTION_CANDIDATE, truth) == ReleaseState.PILOT
    assert next_state(ReleaseState.PILOT, truth) == ReleaseState.PILOT_ACCEPTED

    with pytest.raises(ValueError):
        next_state(ReleaseState.PILOT_ACCEPTED, truth)
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            truth,
            tenant_ids=("*",),
            modules=("all",),
        )
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            truth,
            tenant_ids=("other-tenant",),
            modules=("workforce",),
        )

    active = next_state(
        ReleaseState.PILOT_ACCEPTED,
        truth,
        tenant_ids=(TENANT,),
        modules=("workforce",),
    )
    assert active == ReleaseState.PRODUCTION_ACTIVE
    assert next_state(active, truth) == ReleaseState.STABILIZING
    assert next_state(ReleaseState.STABILIZING, truth) == ReleaseState.CATEGORY_LEADERSHIP
    with pytest.raises(ValueError):
        next_state(ReleaseState.CATEGORY_LEADERSHIP, truth)


def test_pilot_requires_bounded_scope_plan_and_rollback() -> None:
    truth = full_truth()
    with pytest.raises(ValueError):
        next_state(ReleaseState.PRODUCTION_CANDIDATE, replace(truth, pilot_scope=None))
    with pytest.raises(ValueError):
        next_state(ReleaseState.PRODUCTION_CANDIDATE, replace(truth, pilot_plan_ref=""))
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PRODUCTION_CANDIDATE,
            replace(truth, pilot_rollback_ref="rollback:plain-text"),
        )


def test_pilot_signoff_and_external_refs_are_release_bound() -> None:
    truth = full_truth()
    bad_external = dict(truth.external_evidence_refs)
    bad_external[54] = _raw_external_refs()[54]
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.DEVELOPMENT,
            replace(truth, external_evidence_refs=bad_external),
        )

    missing_pilot_ref = replace(truth, pilot_evidence_refs={})
    with pytest.raises(ValueError):
        next_state(ReleaseState.PILOT, missing_pilot_ref)

    bad_signoff = dict(truth.signoff_evidence_refs)
    bad_signoff["security"] = _raw_ref("signoff", "security")
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            replace(truth, signoff_evidence_refs=bad_signoff),
            tenant_ids=(TENANT,),
            modules=("inventory",),
        )


def test_evidence_revocation_blocks_pilot_start_after_rc() -> None:
    truth = full_truth()
    external_items = dict(truth.external_items)
    external_items[54] = False
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PRODUCTION_CANDIDATE,
            replace(truth, external_items=external_items),
        )


def test_evidence_revocation_blocks_category_leadership_after_activation() -> None:
    truth = full_truth()
    external_items = dict(truth.external_items)
    external_items[54] = False
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.STABILIZING,
            replace(truth, external_items=external_items),
        )


def test_stabilization_acceptance_requires_all_release_bound_metrics() -> None:
    truth = full_truth()
    refs = dict(truth.stabilization_evidence_refs)
    refs.pop("no_open_p0")
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.STABILIZING,
            replace(truth, stabilization_evidence_refs=refs),
        )


def test_stabilization_prioritizes_verified_p0_p1() -> None:
    issues = (
        StabilizationIssue(
            "support",
            "friction",
            "slow approval",
            _raw_ref("stabilization", "ticket:2"),
            "P1",
        ),
        StabilizationIssue(
            "monitoring",
            "slow_queries",
            "timeout",
            _raw_ref("stabilization", "trace:1"),
            "P0",
        ),
        StabilizationIssue("rumor", "bugs", "unknown", "ticket:plain-text", "P0"),
    )
    backlog = stabilization_backlog(issues)
    assert [(item.priority, item.source) for item in backlog] == [
        ("P0", "monitoring"),
        ("P1", "support"),
    ]


def test_category_leadership_backlog_is_verified_evidence_bound() -> None:
    signals = (
        BenchmarkSignal(
            "competitor",
            "planogram",
            "new solver",
            _raw_ref("benchmark", "release:1"),
        ),
        BenchmarkSignal("rumor", "jarvis", "unverified", "release:plain-text"),
    )
    assert [signal.source for signal in category_leadership_backlog(signals)] == [
        "competitor"
    ]
