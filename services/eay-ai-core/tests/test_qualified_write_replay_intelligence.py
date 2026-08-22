import asyncio
from datetime import datetime, timedelta, timezone

from app.command_authorization import (
    ActionRisk,
    CommandAuthorizationPolicy,
    IdentityBoundCommand,
    authorize_identity_bound_command,
)
from app.mission_execution import CapabilityExecutionOutcome
from app.playwright_computer_runtime import (
    BrowserAction,
    BrowserActionKind,
    BrowserLocator,
    LocatorKind,
    PlaywrightSessionConfig,
)
from app.playwright_mission_adapter import PlaywrightCapabilityPlan
from app.procedural_memory import (
    ProcedureDemonstration,
    ProcedureStep,
    ProcedureStepKind,
    compile_procedure,
    procedure_step_fingerprint,
)
from app.qualified_write_replay import (
    ReplayDisposition,
    bind_qualified_playwright_write,
    playwright_plan_shape_fingerprint,
    replay_qualified_playwright_write,
)
from app.write_capability_qualification import (
    build_write_capability_candidate,
    compile_qualified_write_capability,
    create_controlled_write_demonstration,
)


NOW = datetime(2026, 8, 18, 8, 20, tzinfo=timezone.utc)
ENV = "d" * 64
TENANT = "tenant://SYNTHETIC_A"
TARGET = "warehouse://SYNTHETIC_A/FULYA_FIXTURE"
EXECUTION_CAPABILITY = "synthetic.inventory.adjust"
PERMISSION = "inventory.adjust"
VERIFIER = "verifier://inventory/authoritative-readback"
HOST = "portal.example.com"


def _read_foundation():
    steps = (
        ProcedureStep(
            step_id="read",
            kind=ProcedureStepKind.READBACK,
            operation_ref="readback://stock",
        ),
    )
    fp = procedure_step_fingerprint(steps)
    demos = [
        ProcedureDemonstration(
            demonstration_id=f"read-{index}",
            tenant_id=TENANT,
            capability_name="synthetic.inventory.read_stock",
            observed_at=NOW + timedelta(minutes=index),
            step_fingerprint=fp,
            successful=True,
            effect_verified=True,
            ambiguous_outcome=False,
            environment_fingerprint=ENV,
            evidence_refs=(f"read://evidence/{index}",),
        )
        for index in (1, 2)
    ]
    return compile_procedure(
        tenant_id=TENANT,
        capability_name="synthetic.inventory.read_stock",
        steps=steps,
        demonstrations=demos,
        minimum_verified_demonstrations=2,
    )


def _candidate(foundation):
    steps = (
        ProcedureStep(
            step_id="locate",
            kind=ProcedureStepKind.ACCESSIBILITY,
            operation_ref="browser://locate",
        ),
        ProcedureStep(
            step_id="submit",
            kind=ProcedureStepKind.ACCESSIBILITY,
            operation_ref="browser://submit",
            side_effect=True,
            expected_effect_ref="effect://stock-delta",
            effect_verifier_ref=VERIFIER,
        ),
        ProcedureStep(
            step_id="readback",
            kind=ProcedureStepKind.READBACK,
            operation_ref="readback://authoritative-stock",
        ),
    )
    return build_write_capability_candidate(
        application_id="synthetic-carsiportal",
        read_foundation=foundation,
        capability_name="synthetic.inventory.adjust.v1",
        execution_capability_ref=EXECUTION_CAPABILITY,
        required_permission=PERMISSION,
        target_scope_ref=TARGET,
        risk=ActionRisk.LOW,
        procedure_steps=steps,
    )


def _policy():
    return CommandAuthorizationPolicy(
        policy_id="policy://replay-test",
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
    )


def _authorization(index, idempotency=None):
    idem = idempotency or f"idem://replay-{index}"
    return authorize_identity_bound_command(
        policy=_policy(),
        command=IdentityBoundCommand(
            command_id=f"cmd-replay-{index}",
            mission_id=f"mission-replay-{index}",
            step_id="adjust",
            principal_ref="principal://user-a",
            identity_evidence_ref="identity://verified-session-a",
            tenant_ref=TENANT,
            capability_ref=EXECUTION_CAPABILITY,
            target_scope_ref=TARGET,
            issued_at=NOW + timedelta(minutes=index),
            risk=ActionRisk.LOW,
            idempotency_key=idem,
            reason_code="WASTE",
            absolute_quantity=3,
            financial_value=42,
        ),
    )


def _qualified():
    foundation = _read_foundation()
    candidate = _candidate(foundation)
    demos = []
    for index in (1, 2):
        auth = _authorization(index, f"idem://training-{index}")
        outcome = CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            evidence_refs=(f"before://{index}", f"after://{index}"),
            transaction_ref=f"tx://training-{index}",
        )
        demos.append(
            create_controlled_write_demonstration(
                candidate=candidate,
                demonstration_id=f"write-{index}",
                observed_at=NOW + timedelta(minutes=index),
                observed_environment_fingerprint=ENV,
                authorization=auth,
                idempotency_key=auth.idempotency_key,
                outcome=outcome,
            )
        )
    return compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=demos,
    )


def _plan(*, quantity="3", button="Apply adjustment"):
    return PlaywrightCapabilityPlan(
        capability_ref=EXECUTION_CAPABILITY,
        session_config=PlaywrightSessionConfig(
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref="auth://browser-session",
            allowed_hosts=frozenset({HOST}),
        ),
        start_url=f"https://{HOST}/inventory",
        actions=(
            BrowserAction(
                action_id="barcode",
                kind=BrowserActionKind.FILL,
                locator=BrowserLocator(kind=LocatorKind.LABEL, value="Barcode"),
                input_value="8690000000001",
            ),
            BrowserAction(
                action_id="quantity",
                kind=BrowserActionKind.FILL,
                locator=BrowserLocator(kind=LocatorKind.LABEL, value="Quantity"),
                input_value=quantity,
            ),
            BrowserAction(
                action_id="submit",
                kind=BrowserActionKind.CLICK,
                locator=BrowserLocator(
                    kind=LocatorKind.ROLE,
                    value="button",
                    accessible_name=button,
                ),
            ),
        ),
        commit_action_id="submit",
    )


def test_plan_shape_fingerprint_excludes_runtime_form_values_but_detects_ui_structure_drift():
    base = _plan(quantity="3")
    different_value = _plan(quantity="5")
    changed_button = _plan(button="Confirm adjustment")

    assert playwright_plan_shape_fingerprint(base) == playwright_plan_shape_fingerprint(different_value)
    assert playwright_plan_shape_fingerprint(base) != playwright_plan_shape_fingerprint(changed_button)


def test_qualified_replay_uses_zero_models_and_requires_authoritative_effect_success():
    capability = _qualified()
    plan = _plan()
    binding = bind_qualified_playwright_write(capability=capability, plan=plan)
    auth = _authorization(10)
    calls = 0

    async def handler(definition, step, state, idempotency_key):
        nonlocal calls
        calls += 1
        assert idempotency_key == auth.idempotency_key
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            evidence_refs=("before://10", "after://7"),
            transaction_ref="tx://replay-10",
        )

    result = asyncio.run(
        replay_qualified_playwright_write(
            capability=capability,
            binding=binding,
            plan=plan,
            handler=handler,
            authorization=auth,
            observed_environment_fingerprint=ENV,
            expected_idempotency_key=auth.idempotency_key,
        )
    )

    assert result.disposition is ReplayDisposition.COMPLETED
    assert result.model_calls == 0
    assert result.effect_verification_required is True
    assert result.mission_summary.checkpoint.status.value == "completed"
    assert calls == 1


def test_environment_or_plan_shape_drift_blocks_before_handler_runs():
    capability = _qualified()
    base_plan = _plan()
    binding = bind_qualified_playwright_write(capability=capability, plan=base_plan)
    auth = _authorization(11)
    calls = 0

    async def handler(definition, step, state, idempotency_key):
        nonlocal calls
        calls += 1
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            evidence_refs=("should://not-run",),
            transaction_ref="tx://should-not-run",
        )

    env_drift = asyncio.run(
        replay_qualified_playwright_write(
            capability=capability,
            binding=binding,
            plan=base_plan,
            handler=handler,
            authorization=auth,
            observed_environment_fingerprint="e" * 64,
            expected_idempotency_key=auth.idempotency_key,
        )
    )
    ui_drift = asyncio.run(
        replay_qualified_playwright_write(
            capability=capability,
            binding=binding,
            plan=_plan(button="Confirm adjustment"),
            handler=handler,
            authorization=auth,
            observed_environment_fingerprint=ENV,
            expected_idempotency_key=auth.idempotency_key,
        )
    )

    assert env_drift.disposition is ReplayDisposition.BLOCKED
    assert "write_replay_environment_drift" in env_drift.blockers
    assert ui_drift.disposition is ReplayDisposition.BLOCKED
    assert "qualified_write_replay_plan_shape_drift" in ui_drift.blockers
    assert calls == 0


def test_ambiguous_write_halts_and_is_never_automatically_retried():
    capability = _qualified()
    plan = _plan()
    binding = bind_qualified_playwright_write(capability=capability, plan=plan)
    auth = _authorization(12)
    calls = 0

    async def handler(definition, step, state, idempotency_key):
        nonlocal calls
        calls += 1
        return CapabilityExecutionOutcome(
            succeeded=False,
            ambiguous_outcome=True,
            evidence_refs=("request://dispatched",),
            error_code="network_timeout_after_submit",
        )

    result = asyncio.run(
        replay_qualified_playwright_write(
            capability=capability,
            binding=binding,
            plan=plan,
            handler=handler,
            authorization=auth,
            observed_environment_fingerprint=ENV,
            expected_idempotency_key=auth.idempotency_key,
        )
    )

    assert result.disposition is ReplayDisposition.HALTED
    assert result.model_calls == 0
    assert calls == 1
    assert result.mission_summary.checkpoint.status.value == "halted"


def test_stale_or_wrong_idempotency_authorization_blocks_before_execution():
    capability = _qualified()
    plan = _plan()
    binding = bind_qualified_playwright_write(capability=capability, plan=plan)
    auth = _authorization(13, "idem://authorized")
    calls = 0

    async def handler(definition, step, state, idempotency_key):
        nonlocal calls
        calls += 1
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=True,
            evidence_refs=("unexpected://execution",),
            transaction_ref="tx://unexpected",
        )

    result = asyncio.run(
        replay_qualified_playwright_write(
            capability=capability,
            binding=binding,
            plan=plan,
            handler=handler,
            authorization=auth,
            observed_environment_fingerprint=ENV,
            expected_idempotency_key="idem://different",
        )
    )

    assert result.disposition is ReplayDisposition.BLOCKED
    assert "write_replay_idempotency_authorization_mismatch" in result.blockers
    assert calls == 0
