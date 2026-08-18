from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from app.release.canonical_evidence_bridge import CanonicalSreEvidence
from app.release.canonical_transition import advance_with_canonical_authority
from app.release.category_leadership import (
    PILOT_METRICS,
    PROD_SIGNOFFS,
    REQUIRED_EXTERNAL,
    REQUIRED_SRE,
    ReleaseScope,
    ReleaseState,
    ReleaseTruth,
    bind_authority_ref,
    bind_release_evidence_ref,
)
from app.sre.chaos_dr import DrResult

ROOT = Path(__file__).resolve().parents[3]
RELEASE = "eay-rc-1"
CANDIDATE = "a" * 40
NOW = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)


def _digest(value: object) -> str:
    return sha256(str(value).encode()).hexdigest()


def _bound(kind: str, value: object) -> str:
    return bind_release_evidence_ref(
        kind,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        artifact_sha256=_digest(value),
    )


def _truth() -> ReleaseTruth:
    pilot_scope = ReleaseScope(
        tenant_ids=("pilot-tenant",),
        modules=("workforce", "inventory"),
        evidence_ref=_bound("scope", "pilot"),
        owner="pilot-owner",
    )
    activation_scope = ReleaseScope(
        tenant_ids=("pilot-tenant",),
        modules=("workforce", "inventory"),
        evidence_ref=_bound("scope", "activation"),
        owner="release-owner",
    )
    return ReleaseTruth(
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        repository_green=True,
        repository_evidence_ref=f"github-status:{CANDIDATE}",
        pilot_scope=pilot_scope,
        pilot_plan_ref=_bound("plan", "pilot-plan"),
        pilot_rollback_ref=_bound("rollback", "pilot-rollback"),
        pilot_metrics={key: True for key in PILOT_METRICS},
        pilot_evidence_refs={key: _bound("pilot", key) for key in PILOT_METRICS},
        activation_scope=activation_scope,
        activation_plan_ref=_bound("plan", "activation-plan"),
        activation_rollback_ref=_bound("rollback", "activation-rollback"),
        signoffs={key: True for key in PROD_SIGNOFFS},
        signoff_evidence_refs={key: _bound("signoff", key) for key in PROD_SIGNOFFS},
    )


def _sre_placeholder() -> CanonicalSreEvidence:
    return CanonicalSreEvidence(
        telemetry_events=(),
        scale_evidence={},
        chaos_results=(),
        dr_result=DrResult("ci", False, None, None, ""),
        observability_artifact_sha256="0" * 64,
        scale_artifact_sha256="0" * 64,
        chaos_artifact_sha256="0" * 64,
        dr_artifact_sha256="0" * 64,
    )


def _source_ref(kind: str, item: int) -> str:
    return f"{kind}-sha256:{_digest(f'{kind}:{item}')}"


def _patch_current_authority(
    monkeypatch: pytest.MonkeyPatch,
    *,
    missing: int | None = None,
) -> None:
    sre = {item: _source_ref("sre", item) for item in REQUIRED_SRE}
    external = {
        item: _source_ref("ledger", item)
        for item in REQUIRED_EXTERNAL
        if item != missing
    }
    monkeypatch.setattr(
        "app.release.canonical_transition.build_canonical_sre_refs",
        lambda *_args, **_kwargs: sre,
    )
    monkeypatch.setattr(
        "app.release.canonical_transition.build_canonical_external_refs",
        lambda *_args, **_kwargs: external,
    )


def test_production_active_revalidates_current_authority_before_stabilization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_authority(monkeypatch)
    state = advance_with_canonical_authority(
        ROOT,
        ReleaseState.PRODUCTION_ACTIVE,
        _truth(),
        sre_evidence=_sre_placeholder(),
        external_records=(),
        tenant_id="pilot-tenant",
        as_of=NOW,
    )
    assert state == ReleaseState.STABILIZING


def test_revoked_or_expired_current_item_blocks_even_if_truth_carries_stale_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth = _truth()
    stale = replace(
        truth,
        external_items={item: True for item in REQUIRED_EXTERNAL},
        external_evidence_refs={
            item: bind_authority_ref(
                "ledger",
                _source_ref("ledger", item),
                release_id=RELEASE,
                candidate_sha=CANDIDATE,
            )
            for item in REQUIRED_EXTERNAL
        },
    )
    _patch_current_authority(monkeypatch, missing=54)

    with pytest.raises(ValueError, match="current canonical 49-55 acceptance evidence"):
        advance_with_canonical_authority(
            ROOT,
            ReleaseState.PRODUCTION_ACTIVE,
            stale,
            sre_evidence=_sre_placeholder(),
            external_records=(),
            tenant_id="pilot-tenant",
            as_of=NOW,
        )


def test_current_authority_is_rebuilt_before_earlier_release_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_authority(monkeypatch, missing=50)
    with pytest.raises(ValueError, match="current canonical 49-55 acceptance evidence"):
        advance_with_canonical_authority(
            ROOT,
            ReleaseState.DEVELOPMENT,
            _truth(),
            sre_evidence=_sre_placeholder(),
            external_records=(),
            tenant_id="pilot-tenant",
            as_of=NOW,
        )
