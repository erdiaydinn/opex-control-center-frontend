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
from app.mission_execution import CapabilityExecutionOutcome
from app.mission_runtime import MissionDefinition, MissionStep
from app.procedural_memory import (
    ProcedureDemonstration,
    ProcedureStatus,
    ProcedureStep,
    ProcedureStepKind,
    compile_procedure,
    procedure_step_fingerprint,
)
from app.write_capability_qualification import (
    WriteQualificationStatus,
    build_write_capability_candidate,
    compile_qualified_write_capability,
    create_controlled_write_demonstration,
    preflight_qualified_write_replay,
)


NOW = datetime(2026, 8, 18, 7, 40, tzinfo=timezone.utc)
ENV = "a" * 64
TENANT = "tenant://SYNTHETIC_A"
TARGET = "warehouse://SYNTHETIC_A/STORE_01"
EXECUTION_CAPABILITY = "synthetic.inventory.adjust"
PERMISSION = "inventory.adjust"


def _read_steps():
    return (
        ProcedureStep(
            step_id="read-stock",
            kind=ProcedureStepKind.READBACK,
            operation_ref="synthetic://inventory/read-stock",
            side_effect=False,
        ),
    )


def _read_foundation(*, verified_count=2):
    steps = _read_steps()
    fingerprint = procedure_step_fingerprint(steps)
    demonstrations = [
        ProcedureDemonstration(
            demonstration_id=f"read-{index}",
            tenant_id=TENANT,
            capability_name="synthetic.inventory.read_stock",
            observed_at=NOW + timedelta(minutes=index),
            step_fingerprint=fingerprint,
            successful=True,
            effect_verified=True,
            ambiguous_outcome=False,
            environment_fingerprint=ENV,
            evidence_refs=(f"evidence://read/{index}",),
        )
        for index in range(verified_count)
    ]
    return compile_procedure(
        tenant_id=TENANT,
        capability_name="synthetic.inventory.read_stock",
        steps=steps,
        demonstrations=demonstrations,
        minimum_verified_demonstrations=2,
    )


def _write_steps():
    return (
        ProcedureStep(
            step_id="locate-sku",
            kind=ProcedureStepKind.ACCESSIBILITY,
            operation_ref="browser://synthetic-carsiportal/locate-sku",
            side_effect=False,
        ),
        ProcedureStep(
            step_id="commit-adjustment",
            kind=ProcedureStepKind.ACCESSIBILITY,
            operation_ref="browser://synthetic-carsiportal/commit-adjustment",
            side_effect=True,
            expected_effect_ref="effect://inventory/stock-delta",
            effect_verifier_ref="verifier://inventory/authoritative-readback",
        ),
        ProcedureStep(
            step_id="read-back-stock",
            kind=ProcedureStepKind.READBACK,
            operation_ref="readback://inventory/authoritative-state",
            side_effect=False,
        ),
    )


def _candidate(*, risk=ActionRisk.LOW, foundation=None):
    return build_write_capability_candidate(
        application_id="synthetic-carsiportal",
        read_foundation=foundation or _read_foundation(),
        capability_name="synthetic.inventory.adjust.v1",
        execution_capability_ref=EXECUTION_CAPABILITY,
        required_permission=PERMISSION,
        target_scope_ref=TARGET,
        risk=risk,
        procedure_steps=_write_steps(),
    )


def _policy():
    return CommandAuthorizationPolicy(
        policy_id="policy://synthetic-inventory-adjust",
        principal_ref="principal://user-a",
        identity_evidence_ref="identity://verified-session-a",
        tenant_ref=TENANT,
        allowed_capabilities=frozenset({EXECUTION_CAPABILITY}),
        allowed_target_scopes=frozenset({TARGET}),
        allowed_reason_codes=frozenset({"WASTE"}),
        max_absolute_quantity=5,
        max_financial_value=100,
        valid_from=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(hours=8),
        command_authorization_max_risk=ActionRisk.MEDIUM,
    )


def _authorization(command_id, idempotency_key, *, risk=ActionRisk.LOW, target=TARGET):
    return authorize_identity_bound_command(
        policy=_policy(),
        command=IdentityBoundCommand(
            command_id=command_id,
            mission_id=f"mission-{command_id}",
            step_id="adjust",
            principal_ref="principal://user-a",
            identity_evidence_ref="identity://verified-session-a",
            tenant_ref=TENANT,
            capability_ref=EXECUTION_CAPABILITY,
            target_scope_ref=target,
            issued_at=NOW,
            risk=risk,
            side_effect=True,
            idempotency_key=idempotency_key,
            reason_code="WASTE",
            absolute_quantity=3,
            financial_value=42,
        ),
    )


def _outcome(tx, *, success=True, verified=True, ambiguous=False):
    return CapabilityExecutionOutcome(
        succeeded=success,
        effect_verified=verified,
        ambiguous_outcome=ambiguous,
        evidence_refs=(f"evidence://before/{tx}", f"evidence://after/{tx}"),
        transaction_ref=tx,
        error_code=("unknown_after_submit" if ambiguous else None),
    )


def _demo(candidate, index, *, idem=None, tx=None, outcome=None, authorization=None):
    idempotency = idem or f"idem://write-{index}"
    auth = authorization or _authorization(f"cmd-{index}", idempotency, risk=candidate.risk)
    return create_controlled_write_demonstration(
        candidate=candidate,
        demonstration_id=f"write-demo-{index}",
        observed_at=NOW + timedelta(minutes=index),
        observed_environment_fingerprint=ENV,
        authorization=auth,
        idempotency_key=idempotency,
        outcome=outcome or _outcome(tx or f"synthetic-tx://{index}"),
        evidence_refs=(f"browser-evidence://{index}",),
    )


def test_write_candidate_requires_validated_reusable_read_foundation():
    candidate_foundation = _read_foundation(verified_count=1)
    assert candidate_foundation.status is ProcedureStatus.CANDIDATE

    with pytest.raises(ValueError, match="write_qualification_requires_validated_read_foundation"):
        _candidate(foundation=candidate_foundation)


def test_two_independent_authorized_effect_verified_writes_qualify_deterministic_replay():
    foundation = _read_foundation()
    candidate = _candidate(foundation=foundation)
    demos = [_demo(candidate, 1), _demo(candidate, 2)]

    qualified = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=demos,
    )

    assert qualified.status is WriteQualificationStatus.QUALIFIED
    assert qualified.deterministic_replay_allowed is True
    assert qualified.procedure.status is ProcedureStatus.VALIDATED
    assert qualified.blockers == ()
    assert qualified.authorization_required_every_execution is True
    assert qualified.effect_verification_required_every_execution is True
    assert qualified.execution_without_fresh_authorization_allowed is False
    assert qualified.execution_capability_ref == EXECUTION_CAPABILITY
    assert qualified.required_permission == PERMISSION
    for demo in demos:
        assert demo.authorization_evidence_ref in demo.demonstration.evidence_refs
        assert demo.transaction_ref in demo.demonstration.evidence_refs


def test_one_verified_write_never_qualifies_replay():
    foundation = _read_foundation()
    candidate = _candidate(foundation=foundation)

    result = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=[_demo(candidate, 1)],
    )

    assert result.status is WriteQualificationStatus.BLOCKED
    assert result.deterministic_replay_allowed is False
    assert "write_qualification_verified_demonstrations_insufficient" in result.blockers


def test_duplicate_idempotency_or_transaction_breaks_independent_write_proof():
    foundation = _read_foundation()
    candidate = _candidate(foundation=foundation)
    same_idem = "idem://same"
    duplicate_idem = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=[
            _demo(candidate, 1, idem=same_idem, tx="synthetic-tx://1"),
            _demo(candidate, 2, idem=same_idem, tx="synthetic-tx://2"),
        ],
    )
    duplicate_tx = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=[
            _demo(candidate, 3, tx="synthetic-tx://same"),
            _demo(candidate, 4, tx="synthetic-tx://same"),
        ],
    )

    assert duplicate_idem.deterministic_replay_allowed is False
    assert "write_qualification_verified_idempotency_not_independent" in duplicate_idem.blockers
    assert duplicate_tx.deterministic_replay_allowed is False
    assert "write_qualification_verified_transactions_not_independent" in duplicate_tx.blockers


def test_ambiguous_or_unverified_write_never_counts_as_qualification_evidence():
    foundation = _read_foundation()
    candidate = _candidate(foundation=foundation)
    ambiguous = _demo(
        candidate,
        1,
        outcome=_outcome("synthetic-tx://unknown", success=False, verified=False, ambiguous=True),
    )
    unverified = _demo(
        candidate,
        2,
        outcome=_outcome("synthetic-tx://unverified", success=True, verified=False, ambiguous=False),
    )

    result = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=[ambiguous, unverified],
    )

    assert result.deterministic_replay_allowed is False
    assert "write_qualification_verified_demonstrations_insufficient" in result.blockers
    assert "write_qualification_contains_ambiguous_demonstration" in result.blockers


def test_demonstration_requires_exact_capability_target_risk_and_authorized_idempotency():
    candidate = _candidate()
    good_auth = _authorization("cmd-good", "idem://authorized", risk=ActionRisk.LOW)

    with pytest.raises(ValueError, match="write_demonstration_idempotency_authorization_mismatch"):
        _demo(candidate, 1, idem="idem://different", authorization=good_auth)

    medium_auth = _authorization("cmd-medium", "idem://medium", risk=ActionRisk.MEDIUM)
    with pytest.raises(ValueError, match="write_demonstration_risk_authorization_mismatch"):
        _demo(candidate, 2, idem="idem://medium", authorization=medium_auth)

    wrong_target_auth = _authorization("cmd-target", "idem://target", target="warehouse://SYNTHETIC_A/STORE_99")
    assert wrong_target_auth.disposition is AuthorizationDisposition.DENY
    with pytest.raises(ValueError, match="write_demonstration_requires_allowed_command_authorization"):
        _demo(candidate, 3, idem="idem://target", authorization=wrong_target_auth)


def test_high_risk_command_only_authorization_cannot_be_used_as_controlled_write_proof():
    candidate = _candidate(risk=ActionRisk.HIGH)
    auth = _authorization("cmd-high", "idem://high", risk=ActionRisk.HIGH)

    assert auth.disposition is AuthorizationDisposition.REQUIRE_ADDITIONAL_APPROVAL
    with pytest.raises(ValueError, match="write_demonstration_requires_allowed_command_authorization"):
        _demo(candidate, 1, idem="idem://high", authorization=auth)


def test_qualified_replay_requires_fresh_matching_authorization_environment_risk_and_idempotency():
    foundation = _read_foundation()
    candidate = _candidate(foundation=foundation)
    qualified = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=[_demo(candidate, 1), _demo(candidate, 2)],
    )
    fresh = _authorization("cmd-replay", "idem://replay", risk=ActionRisk.LOW)

    allowed = preflight_qualified_write_replay(
        capability=qualified,
        authorization=fresh,
        observed_environment_fingerprint=ENV,
        expected_idempotency_key="idem://replay",
    )
    wrong_idempotency = preflight_qualified_write_replay(
        capability=qualified,
        authorization=fresh,
        observed_environment_fingerprint=ENV,
        expected_idempotency_key="idem://other",
    )
    drifted = preflight_qualified_write_replay(
        capability=qualified,
        authorization=fresh,
        observed_environment_fingerprint="b" * 64,
        expected_idempotency_key="idem://replay",
    )
    risk_mismatch = preflight_qualified_write_replay(
        capability=qualified,
        authorization=_authorization("cmd-medium-replay", "idem://medium-replay", risk=ActionRisk.MEDIUM),
        observed_environment_fingerprint=ENV,
        expected_idempotency_key="idem://medium-replay",
    )

    assert allowed.allowed is True
    assert allowed.authorization_evidence_ref == fresh.authorization_evidence_ref
    assert allowed.idempotency_key == "idem://replay"
    assert allowed.effect_verification_required is True
    assert wrong_idempotency.allowed is False
    assert "write_replay_idempotency_authorization_mismatch" in wrong_idempotency.blockers
    assert drifted.allowed is False
    assert "write_replay_environment_drift" in drifted.blockers
    assert risk_mismatch.allowed is False
    assert "write_replay_risk_authorization_mismatch" in risk_mismatch.blockers


def test_mission_command_checker_rejects_authorization_bound_to_different_idempotency():
    auth = _authorization("cmd-checker", "idem://authorized", risk=ActionRisk.LOW)
    checker = build_mission_command_authorization_checker((auth,))
    definition = MissionDefinition(
        mission_id="mission-cmd-checker",
        objective="Synthetic controlled adjustment",
        tenant_id="SYNTHETIC_A",
        steps=(
            MissionStep(
                step_id="adjust",
                description="Synthetic adjustment",
                side_effect=True,
                required_permission=PERMISSION,
                idempotency_key="idem://different",
                effect_verifier_ref="verifier://inventory/readback",
            ),
        ),
    )

    # Bind the envelope to the same mission/step while preserving its authorized idempotency.
    rebound = auth.model_copy(update={"mission_id": definition.mission_id, "step_id": "adjust"})
    checker = build_mission_command_authorization_checker((rebound,))
    decision = asyncio.run(checker(definition, definition.steps[0], EXECUTION_CAPABILITY))

    assert decision.allowed is False
    assert decision.reason_code == "command_authorization_idempotency_mismatch"


def test_foreign_demonstration_cannot_silently_help_qualification():
    foundation = _read_foundation()
    candidate = _candidate(foundation=foundation)
    first = _demo(candidate, 1)
    foreign = _demo(candidate, 2).model_copy(update={"candidate_id": "f" * 64})

    result = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=[first, foreign],
    )

    assert result.deterministic_replay_allowed is False
    assert "write_qualification_contains_foreign_demonstration" in result.blockers
    assert "write_qualification_verified_demonstrations_insufficient" in result.blockers
