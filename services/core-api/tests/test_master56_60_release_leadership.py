from dataclasses import replace
from hashlib import sha256

import pytest

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

CANDIDATE = "a" * 40
CHAOS_SCENARIOS = tuple(f"scenario-{index}" for index in range(1, 15))


def _ref(prefix: str, value: object) -> str:
    digest = sha256(str(value).encode()).hexdigest()
    return f"{prefix}-sha256:{digest}"


def _artifact(value: object) -> str:
    return sha256(str(value).encode()).hexdigest()


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


def _sre_refs() -> dict[int, str]:
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


def full_truth() -> ReleaseTruth:
    pilot_scope = ReleaseScope(
        tenant_ids=("pilot-tenant",),
        modules=("workforce", "inventory"),
        evidence_ref=_ref("scope", "pilot"),
        owner="pilot-owner",
    )
    activation_scope = ReleaseScope(
        tenant_ids=("pilot-tenant",),
        modules=("workforce", "inventory"),
        evidence_ref=_ref("scope", "activation"),
        owner="release-owner",
    )
    return ReleaseTruth(
        release_id="eay-rc-1",
        candidate_sha=CANDIDATE,
        repository_green=True,
        repository_evidence_ref=f"github-status:{CANDIDATE}",
        sre_items={item: True for item in REQUIRED_SRE},
        sre_evidence_refs=_sre_refs(),
        external_items={item: True for item in REQUIRED_EXTERNAL},
        external_evidence_refs={item: _ref("ledger", item) for item in REQUIRED_EXTERNAL},
        pilot_scope=pilot_scope,
        pilot_plan_ref=_ref("plan", "pilot-plan"),
        pilot_rollback_ref=_ref("rollback", "pilot-rollback"),
        pilot_metrics={key: True for key in PILOT_METRICS},
        pilot_evidence_refs={key: _ref("pilot", key) for key in PILOT_METRICS},
        activation_scope=activation_scope,
        activation_plan_ref=_ref("plan", "activation-plan"),
        activation_rollback_ref=_ref("rollback", "activation-rollback"),
        signoffs={key: True for key in PROD_SIGNOFFS},
        signoff_evidence_refs={key: _ref("signoff", key) for key in PROD_SIGNOFFS},
        stabilization_metrics={key: True for key in STABILIZATION_METRICS},
        stabilization_evidence_refs={
            key: _ref("stabilization", key) for key in STABILIZATION_METRICS
        },
    )


def test_canonical_sre_bridge_requires_real_complete_authority_evidence() -> None:
    refs = _sre_refs()
    assert set(refs) == set(REQUIRED_SRE)
    assert all(value.startswith("sre-sha256:") for value in refs.values())

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
                release_id="eay-rc-1",
                candidate_sha=CANDIDATE,
                repository_green=True,
                repository_evidence_ref=f"github-status:{CANDIDATE}",
            ),
        )


def test_boolean_only_external_or_sre_truth_cannot_create_rc() -> None:
    truth = ReleaseTruth(
        release_id="eay-rc-1",
        candidate_sha=CANDIDATE,
        repository_green=True,
        repository_evidence_ref=f"github-status:{CANDIDATE}",
        sre_items={item: True for item in REQUIRED_SRE},
        external_items={item: True for item in REQUIRED_EXTERNAL},
    )
    with pytest.raises(ValueError):
        next_state(ReleaseState.DEVELOPMENT, truth)


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
        tenant_ids=("pilot-tenant",),
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


def test_pilot_signoff_and_external_refs_are_hash_bound() -> None:
    truth = full_truth()
    bad_external = dict(truth.external_evidence_refs)
    bad_external[54] = "ledger:plain-text"
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.DEVELOPMENT,
            replace(truth, external_evidence_refs=bad_external),
        )

    missing_pilot_ref = replace(truth, pilot_evidence_refs={})
    with pytest.raises(ValueError):
        next_state(ReleaseState.PILOT, missing_pilot_ref)

    bad_signoff = dict(truth.signoff_evidence_refs)
    bad_signoff["security"] = "signoff:plain-text"
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            replace(truth, signoff_evidence_refs=bad_signoff),
            tenant_ids=("pilot-tenant",),
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


def test_stabilization_acceptance_requires_all_hash_bound_metrics() -> None:
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
            _ref("stabilization", "ticket:2"),
            "P1",
        ),
        StabilizationIssue(
            "monitoring",
            "slow_queries",
            "timeout",
            _ref("stabilization", "trace:1"),
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
            _ref("benchmark", "release:1"),
        ),
        BenchmarkSignal("rumor", "jarvis", "unverified", "release:plain-text"),
    )
    assert [signal.source for signal in category_leadership_backlog(signals)] == [
        "competitor"
    ]
