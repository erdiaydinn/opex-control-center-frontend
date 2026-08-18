import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.command_authorization import (
    ActionRisk,
    AuthorizationDisposition,
    CommandAuthorizationPolicy,
    IdentityBoundCommand,
    authorize_identity_bound_command,
    build_mission_command_authorization_checker,
)
from app.engine_gateway import EngineGateway
from app.mission_execution import CapabilityExecutionOutcome, MissionExecutionKind, MissionExecutionSpec, execute_mission_until_blocked
from app.mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint


NOW = datetime(2026, 8, 18, 6, 55, tzinfo=timezone.utc)


def _policy():
    return CommandAuthorizationPolicy(
        policy_id="policy://routine-inventory-adjust-v1",
        principal_ref="principal://user-a",
        identity_evidence_ref="identity://session-verified-1",
        tenant_ref="tenant://SYNTHETIC_A",
        allowed_capabilities=frozenset({"inventory.adjust"}),
        allowed_target_scopes=frozenset({"warehouse://SYNTHETIC_A/STORE_01"}),
        allowed_reason_codes=frozenset({"DAMAGE", "WASTE"}),
        max_absolute_quantity=5,
        max_financial_value=100,
        valid_from=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(hours=8),
        command_authorization_max_risk=ActionRisk.MEDIUM,
    )


def _command(**overrides):
    payload = dict(
        command_id="cmd-001",
        mission_id="mission-001",
        step_id="adjust",
        principal_ref="principal://user-a",
        identity_evidence_ref="identity://session-verified-1",
        tenant_ref="tenant://SYNTHETIC_A",
        capability_ref="inventory.adjust",
        target_scope_ref="warehouse://SYNTHETIC_A/STORE_01",
        issued_at=NOW,
        risk=ActionRisk.LOW,
        side_effect=True,
        idempotency_key="idem://cmd-001",
        reason_code="WASTE",
        absolute_quantity=3,
        financial_value=42,
    )
    payload.update(overrides)
    return IdentityBoundCommand(**payload)


def test_routine_identity_bound_command_is_itself_authorization_without_second_confirmation():
    first = authorize_identity_bound_command(policy=_policy(), command=_command())
    second = authorize_identity_bound_command(policy=_policy(), command=_command())

    assert first.disposition is AuthorizationDisposition.ALLOW_FROM_COMMAND
    assert first.command_counts_as_approval is True
    assert first.blockers == ()
    assert first.authorization_evidence_ref.startswith("command-authz://")
    assert first.authorization_evidence_ref == second.authorization_evidence_ref


def test_wrong_scope_or_identity_or_tenant_is_denied_not_escalated():
    cases = (
        (_command(target_scope_ref="warehouse://SYNTHETIC_A/STORE_99"), "target_scope_not_allowed"),
        (_command(identity_evidence_ref="identity://forged"), "identity_evidence_mismatch"),
        (_command(tenant_ref="tenant://SYNTHETIC_B"), "tenant_mismatch"),
    )
    for command, blocker in cases:
        result = authorize_identity_bound_command(policy=_policy(), command=command)
        assert result.disposition is AuthorizationDisposition.DENY
        assert blocker in result.blockers
        assert result.authorization_evidence_ref is None
        assert result.command_counts_as_approval is False


def test_high_risk_bulk_irreversible_or_limit_excess_requires_additional_approval():
    commands = (
        _command(risk=ActionRisk.HIGH),
        _command(bulk=True),
        _command(irreversible=True),
        _command(absolute_quantity=6),
        _command(financial_value=101),
    )
    for command in commands:
        result = authorize_identity_bound_command(policy=_policy(), command=command)
        assert result.disposition is AuthorizationDisposition.REQUIRE_ADDITIONAL_APPROVAL
        assert result.blockers
        assert result.command_counts_as_approval is False


def test_bounded_policy_cannot_be_bypassed_by_omitting_quantity_or_financial_value():
    quantity_missing = authorize_identity_bound_command(
        policy=_policy(), command=_command(absolute_quantity=None)
    )
    value_missing = authorize_identity_bound_command(
        policy=_policy(), command=_command(financial_value=None)
    )

    assert quantity_missing.disposition is AuthorizationDisposition.REQUIRE_ADDITIONAL_APPROVAL
    assert "quantity_missing_for_bounded_policy" in quantity_missing.blockers
    assert value_missing.disposition is AuthorizationDisposition.REQUIRE_ADDITIONAL_APPROVAL
    assert "financial_value_missing_for_bounded_policy" in value_missing.blockers


def test_expired_command_and_wrong_reason_fail_closed():
    expired = authorize_identity_bound_command(
        policy=_policy(), command=_command(issued_at=NOW + timedelta(days=1))
    )
    wrong_reason = authorize_identity_bound_command(
        policy=_policy(), command=_command(reason_code="OTHER")
    )

    assert expired.disposition is AuthorizationDisposition.DENY
    assert "command_outside_policy_validity_window" in expired.blockers
    assert wrong_reason.disposition is AuthorizationDisposition.DENY
    assert "reason_code_not_allowed" in wrong_reason.blockers


def test_side_effect_command_requires_idempotency_key_before_authorization():
    with pytest.raises(ValueError, match="identity_bound_side_effect_requires_idempotency_key"):
        _command(idempotency_key=None)


def test_generator_backed_mission_checker_binds_evidence_to_exact_step_and_capability():
    envelope = authorize_identity_bound_command(policy=_policy(), command=_command())
    checker = build_mission_command_authorization_checker(item for item in (envelope,))
    definition = MissionDefinition(
        mission_id="mission-001",
        objective="Synthetic inventory adjustment",
        tenant_id="SYNTHETIC_A",
        steps=(
            MissionStep(
                step_id="adjust",
                description="Adjust synthetic stock",
                side_effect=True,
                required_permission="inventory.adjust",
                idempotency_key="idem://cmd-001",
                effect_verifier_ref="fixture://readback",
            ),
        ),
    )

    allowed = asyncio.run(checker(definition, definition.steps[0], "inventory.adjust"))
    wrong_capability = asyncio.run(checker(definition, definition.steps[0], "inventory.delete"))

    assert allowed.allowed is True
    assert allowed.evidence_ref == envelope.authorization_evidence_ref
    assert wrong_capability.allowed is False
    assert wrong_capability.reason_code == "command_authorization_capability_mismatch"


def test_duplicate_authorization_for_same_mission_step_is_rejected():
    first = authorize_identity_bound_command(policy=_policy(), command=_command(command_id="cmd-a"))
    second = authorize_identity_bound_command(policy=_policy(), command=_command(command_id="cmd-b"))

    with pytest.raises(ValueError, match="duplicate_command_authorization_for_mission_step"):
        build_mission_command_authorization_checker((first, second))


def test_one_command_authorization_composes_with_mission_execution_and_effect_verification():
    envelope = authorize_identity_bound_command(policy=_policy(), command=_command())
    checker = build_mission_command_authorization_checker((envelope,))
    definition = MissionDefinition(
        mission_id="mission-001",
        objective="Synthetic stock -3 with authoritative readback",
        tenant_id="SYNTHETIC_A",
        steps=(
            MissionStep(
                step_id="adjust",
                description="Adjust synthetic stock",
                side_effect=True,
                required_permission="inventory.adjust",
                idempotency_key="idem://cmd-001",
                effect_verifier_ref="fixture://readback",
            ),
        ),
    )

    async def handler(definition, step, state, idempotency_key):
        assert idempotency_key == "idem://cmd-001"
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            evidence_refs=("fixture://stock-before/10", "fixture://stock-after/7"),
            transaction_ref="fixture-tx://001",
        )

    summary = asyncio.run(
        execute_mission_until_blocked(
            definition=definition,
            checkpoint=new_checkpoint(definition),
            specs=(
                MissionExecutionSpec(
                    step_id="adjust",
                    kind=MissionExecutionKind.CAPABILITY,
                    capability_ref="inventory.adjust",
                ),
            ),
            gateway=EngineGateway([]),
            reasoning_evidence_writer=lambda receipt: "unused",
            capability_handlers={"inventory.adjust": handler},
            authorization_checker=checker,
        )
    )

    assert summary.checkpoint.status is MissionStatus.COMPLETED
    state = summary.checkpoint.steps[0]
    assert envelope.authorization_evidence_ref in state.evidence_refs
    assert "fixture://stock-after/7" in state.evidence_refs
    assert "fixture-tx://001" in state.evidence_refs
