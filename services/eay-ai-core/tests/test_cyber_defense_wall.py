from datetime import UTC, datetime, timedelta

import pytest

from app.cyber_defense_wall import (
    DEFAULT_REQUIRED_CONTROLS,
    AttackChainStage,
    DefenseControlKind,
    DefenseWall,
    WallReadiness,
    assess_combined_attack_chain,
    assess_wall,
    build_control_evidence,
)

NOW = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)


def _controls_for_wall(wall: DefenseWall, *, production: bool = False):
    stages = tuple(AttackChainStage)
    return tuple(
        build_control_evidence(
            control_id=control_id,
            wall=wall,
            kind=DefenseControlKind.PREVENT,
            stage_coverage=stages,
            evidence_refs=(f"evidence:{control_id}",),
            observed_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(hours=23),
            enabled=True,
            fail_closed=True,
            company_scoped=True,
            production_observed=production,
        )
        for control_id in DEFAULT_REQUIRED_CONTROLS[wall]
    )


def test_all_eight_walls_require_complete_fail_closed_controls():
    for wall in DefenseWall:
        receipt = assess_wall(wall=wall, controls=_controls_for_wall(wall), as_of=NOW)
        assert receipt.readiness is WallReadiness.READY
        assert receipt.production_ready_claim_allowed is False
        assert receipt.execution_authority_granted is False


def test_missing_required_control_blocks_wall():
    wall = DefenseWall.IDENTITY
    controls = _controls_for_wall(wall)[:-1]
    receipt = assess_wall(wall=wall, controls=controls, as_of=NOW)
    assert receipt.readiness is WallReadiness.BLOCKED
    assert receipt.missing_control_ids


def test_stale_control_blocks_wall():
    wall = DefenseWall.DATA_TENANT
    controls = list(_controls_for_wall(wall))
    first = controls[0]
    controls[0] = build_control_evidence(
        control_id=first.control_id,
        wall=wall,
        kind=first.kind,
        stage_coverage=first.stage_coverage,
        evidence_refs=first.evidence_refs,
        observed_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(seconds=1),
        enabled=True,
        fail_closed=True,
        company_scoped=True,
    )
    receipt = assess_wall(wall=wall, controls=tuple(controls), as_of=NOW)
    assert receipt.readiness is WallReadiness.BLOCKED
    assert first.control_id in receipt.stale_control_ids


def test_non_fail_closed_control_degrades_wall():
    wall = DefenseWall.APPLICATION_API
    controls = list(_controls_for_wall(wall))
    first = controls[0]
    controls[0] = build_control_evidence(
        control_id=first.control_id,
        wall=wall,
        kind=first.kind,
        stage_coverage=first.stage_coverage,
        evidence_refs=first.evidence_refs,
        observed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        enabled=True,
        fail_closed=False,
        company_scoped=True,
    )
    receipt = assess_wall(wall=wall, controls=tuple(controls), as_of=NOW)
    assert receipt.readiness is WallReadiness.DEGRADED
    assert receipt.production_ready_claim_allowed is False


def test_production_claim_requires_real_company_production_evidence():
    wall = DefenseWall.RUNTIME_DETECTION
    repo_only = assess_wall(wall=wall, controls=_controls_for_wall(wall), as_of=NOW)
    production = assess_wall(
        wall=wall,
        controls=_controls_for_wall(wall, production=True),
        as_of=NOW,
    )
    assert repo_only.production_ready_claim_allowed is False
    assert production.production_ready_claim_allowed is True


def test_single_security_wall_is_not_defense_in_depth():
    edge = assess_wall(
        wall=DefenseWall.EDGE,
        controls=_controls_for_wall(DefenseWall.EDGE),
        as_of=NOW,
    )
    result = assess_combined_attack_chain(
        chain_id="combined-threat:single-wall",
        stages=tuple(AttackChainStage),
        wall_receipts=(edge,),
        as_of=NOW,
    )
    assert result.defense_in_depth_complete is False
    assert result.single_point_of_failure_stages
    assert result.production_security_claim_allowed is False


def test_multiple_independent_walls_remove_single_point_of_failure():
    edge = assess_wall(
        wall=DefenseWall.EDGE,
        controls=_controls_for_wall(DefenseWall.EDGE),
        as_of=NOW,
    )
    identity = assess_wall(
        wall=DefenseWall.IDENTITY,
        controls=_controls_for_wall(DefenseWall.IDENTITY),
        as_of=NOW,
    )
    result = assess_combined_attack_chain(
        chain_id="combined-threat:layered",
        stages=tuple(AttackChainStage),
        wall_receipts=(edge, identity),
        as_of=NOW,
    )
    assert result.uncovered_stages == ()
    assert result.single_point_of_failure_stages == ()
    assert result.defense_in_depth_complete is True
    assert result.production_security_claim_allowed is False


def test_offensive_or_execution_authority_is_rejected():
    control = _controls_for_wall(DefenseWall.AI_AGENT)[0]
    payload = control.model_dump(mode="json")
    payload["automatic_offensive_action_permitted"] = True
    with pytest.raises(ValueError, match="offensive_or_execution_authority_forbidden"):
        control.__class__.model_validate(payload)


def test_production_security_claim_cannot_be_inferred_from_repository_evidence():
    receipts = tuple(
        assess_wall(wall=wall, controls=_controls_for_wall(wall), as_of=NOW)
        for wall in DefenseWall
    )
    result = assess_combined_attack_chain(
        chain_id="combined-threat:all-repository-walls",
        stages=tuple(AttackChainStage),
        wall_receipts=receipts,
        as_of=NOW,
    )
    assert result.defense_in_depth_complete is True
    assert result.production_security_claim_allowed is False
    assert result.offensive_simulation_permitted is False
    assert result.production_mutation_permitted is False
    assert result.execution_authority_granted is False
