import pytest

from app.release.category_leadership import (
    PILOT_METRICS,
    PROD_SIGNOFFS,
    REQUIRED_EXTERNAL,
    REQUIRED_SRE,
    BenchmarkSignal,
    ReleaseState,
    ReleaseTruth,
    StabilizationIssue,
    category_leadership_backlog,
    next_state,
    stabilization_backlog,
)


def full_truth() -> ReleaseTruth:
    return ReleaseTruth(
        repository_green=True,
        repository_evidence_ref="ci:canonical-exact-head",
        sre_items={item: True for item in REQUIRED_SRE},
        sre_evidence_refs={item: f"sre:{item}" for item in REQUIRED_SRE},
        external_items={item: True for item in REQUIRED_EXTERNAL},
        external_evidence_refs={item: f"external:{item}" for item in REQUIRED_EXTERNAL},
        pilot_metrics={key: True for key in PILOT_METRICS},
        pilot_evidence_refs={key: f"pilot:{key}" for key in PILOT_METRICS},
        signoffs={key: True for key in PROD_SIGNOFFS},
        signoff_evidence_refs={key: f"signoff:{key}" for key in PROD_SIGNOFFS},
    )


def test_repository_green_alone_can_never_create_rc() -> None:
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.DEVELOPMENT,
            ReleaseTruth(repository_green=True, repository_evidence_ref="ci:green"),
        )


def test_boolean_only_external_or_sre_truth_cannot_create_rc() -> None:
    truth = ReleaseTruth(
        repository_green=True,
        repository_evidence_ref="ci:green",
        sre_items={item: True for item in REQUIRED_SRE},
        external_items={item: True for item in REQUIRED_EXTERNAL},
    )
    with pytest.raises(ValueError):
        next_state(ReleaseState.DEVELOPMENT, truth)


def test_release_chain_requires_pilot_and_controlled_tenant_module_activation() -> None:
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
    assert (
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            truth,
            tenant_ids=("pilot-tenant",),
            modules=("workforce",),
        )
        == ReleaseState.PRODUCTION_ACTIVE
    )


def test_pilot_and_signoff_booleans_require_provenance() -> None:
    truth = full_truth()
    missing_pilot_ref = ReleaseTruth(
        **{
            **truth.__dict__,
            "pilot_evidence_refs": {},
        }
    )
    with pytest.raises(ValueError):
        next_state(ReleaseState.PILOT, missing_pilot_ref)

    missing_signoff_ref = ReleaseTruth(
        **{
            **truth.__dict__,
            "signoff_evidence_refs": {},
        }
    )
    with pytest.raises(ValueError):
        next_state(
            ReleaseState.PILOT_ACCEPTED,
            missing_signoff_ref,
            tenant_ids=("pilot-tenant",),
            modules=("inventory",),
        )


def test_evidence_revocation_blocks_pilot_start_after_rc() -> None:
    truth = full_truth()
    external_items = dict(truth.external_items)
    external_items[54] = False
    revoked = ReleaseTruth(**{**truth.__dict__, "external_items": external_items})
    with pytest.raises(ValueError):
        next_state(ReleaseState.PRODUCTION_CANDIDATE, revoked)


def test_stabilization_prioritizes_provenance_bound_p0_p1() -> None:
    issues = (
        StabilizationIssue("support", "friction", "slow approval", "ticket:2", "P1"),
        StabilizationIssue("monitoring", "slow_queries", "timeout", "trace:1", "P0"),
        StabilizationIssue("rumor", "bugs", "unknown", "", "P0"),
    )
    backlog = stabilization_backlog(issues)
    assert [(item.priority, item.source) for item in backlog] == [
        ("P0", "monitoring"),
        ("P1", "support"),
    ]


def test_category_leadership_backlog_is_provenance_bound() -> None:
    signals = (
        BenchmarkSignal("competitor", "planogram", "new solver", "release:1"),
        BenchmarkSignal("rumor", "jarvis", "unverified", ""),
    )
    assert [signal.source for signal in category_leadership_backlog(signals)] == [
        "competitor"
    ]
