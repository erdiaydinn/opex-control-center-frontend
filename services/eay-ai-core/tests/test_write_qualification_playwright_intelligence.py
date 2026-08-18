import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.command_authorization import (
    ActionRisk,
    CommandAuthorizationPolicy,
    IdentityBoundCommand,
    authorize_identity_bound_command,
    build_mission_command_authorization_checker,
)
from app.engine_gateway import EngineGateway
from app.mission_execution import (
    MissionExecutionKind,
    MissionExecutionSpec,
    execute_mission_until_blocked,
)
from app.mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint
from app.playwright_computer_runtime import (
    BrowserAction,
    BrowserActionKind,
    BrowserActionReceipt,
    BrowserLocator,
    LocatorKind,
    PlaywrightSessionConfig,
)
from app.playwright_mission_adapter import (
    BrowserEffectVerification,
    EffectVerificationStatus,
    PlaywrightCapabilityPlan,
    build_playwright_capability_handler,
)
from app.procedural_memory import (
    ProcedureDemonstration,
    ProcedureStep,
    ProcedureStepKind,
    compile_procedure,
    procedure_step_fingerprint,
)
from app.write_capability_qualification import (
    WriteQualificationStatus,
    build_write_capability_candidate,
    compile_qualified_write_capability,
    preflight_qualified_write_replay,
)
from app.write_qualification_mission import create_write_demonstration_from_completed_mission


NOW = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)
ENV = "c" * 64
TENANT = "tenant://SYNTHETIC_A"
TARGET = "warehouse://SYNTHETIC_A/FULYA_FIXTURE"
EXECUTION_CAPABILITY = "synthetic.inventory.adjust"
PERMISSION = "inventory.adjust"
HOST = "portal.example.com"
VERIFIER = "verifier://inventory/authoritative-readback"
AUTH_CONTEXT = "auth://verified-browser-session"


class FakeSession:
    def __init__(self, *, auth_context_ref=AUTH_CONTEXT):
        self.auth_context_ref = auth_context_ref
        self.actions = []
        self.closed = False
        self.goto_url = None

    def goto(self, url):
        self.goto_url = url

    def perform(self, action):
        self.actions.append(action.action_id)
        return BrowserActionReceipt(
            action_id=action.action_id,
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=self.auth_context_ref,
            locator_kind=action.locator.kind,
            action_kind=action.kind,
            completed=True,
            page_url_after=f"https://{HOST}/inventory",
        )

    def close(self):
        self.closed = True


def _read_foundation():
    steps = (
        ProcedureStep(
            step_id="read-stock",
            kind=ProcedureStepKind.READBACK,
            operation_ref="readback://synthetic-inventory/stock",
        ),
    )
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
            evidence_refs=(f"read-evidence://{index}",),
        )
        for index in (1, 2)
    ]
    return compile_procedure(
        tenant_id=TENANT,
        capability_name="synthetic.inventory.read_stock",
        steps=steps,
        demonstrations=demonstrations,
        minimum_verified_demonstrations=2,
    )


def _candidate():
    return build_write_capability_candidate(
        application_id="synthetic-carsiportal",
        read_foundation=_read_foundation(),
        capability_name="synthetic.inventory.adjust.v1",
        execution_capability_ref=EXECUTION_CAPABILITY,
        required_permission=PERMISSION,
        target_scope_ref=TARGET,
        risk=ActionRisk.LOW,
        procedure_steps=(
            ProcedureStep(
                step_id="locate",
                kind=ProcedureStepKind.ACCESSIBILITY,
                operation_ref="browser://synthetic-carsiportal/locate-sku",
            ),
            ProcedureStep(
                step_id="submit",
                kind=ProcedureStepKind.ACCESSIBILITY,
                operation_ref="browser://synthetic-carsiportal/submit-adjustment",
                side_effect=True,
                expected_effect_ref="effect://inventory/stock-delta",
                effect_verifier_ref=VERIFIER,
            ),
            ProcedureStep(
                step_id="readback",
                kind=ProcedureStepKind.READBACK,
                operation_ref="readback://synthetic-inventory/authoritative-state",
            ),
        ),
    )


def _policy():
    return CommandAuthorizationPolicy(
        policy_id="policy://synthetic-routine-adjustment",
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


def _authorization(run_index, *, idempotency=None):
    idem = idempotency or f"idem://vertical-{run_index}"
    return authorize_identity_bound_command(
        policy=_policy(),
        command=IdentityBoundCommand(
            command_id=f"cmd-vertical-{run_index}",
            mission_id=f"mission-vertical-{run_index}",
            step_id="adjust",
            principal_ref="principal://user-a",
            identity_evidence_ref="identity://verified-session-a",
            tenant_ref=TENANT,
            capability_ref=EXECUTION_CAPABILITY,
            target_scope_ref=TARGET,
            issued_at=NOW + timedelta(minutes=run_index),
            risk=ActionRisk.LOW,
            idempotency_key=idem,
            reason_code="WASTE",
            absolute_quantity=3,
            financial_value=42,
        ),
    )


def _playwright_plan():
    return PlaywrightCapabilityPlan(
        capability_ref=EXECUTION_CAPABILITY,
        session_config=PlaywrightSessionConfig(
            application_id="synthetic-carsiportal",
            tenant_scope_ref=TENANT,
            auth_context_ref=AUTH_CONTEXT,
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
                input_value="3",
            ),
            BrowserAction(
                action_id="submit",
                kind=BrowserActionKind.CLICK,
                locator=BrowserLocator(
                    kind=LocatorKind.ROLE,
                    value="button",
                    accessible_name="Apply adjustment",
                ),
            ),
        ),
        commit_action_id="submit",
    )


def _execute_verified_browser_mission(run_index):
    authorization = _authorization(run_index)
    definition = MissionDefinition(
        mission_id=authorization.mission_id,
        objective="Synthetic scoped stock adjustment with authoritative verification",
        tenant_id=TENANT,
        steps=(
            MissionStep(
                step_id="adjust",
                description="Apply synthetic stock adjustment",
                side_effect=True,
                required_permission=PERMISSION,
                idempotency_key=authorization.idempotency_key,
                effect_verifier_ref=VERIFIER,
            ),
        ),
    )
    spec = MissionExecutionSpec(
        step_id="adjust",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref=EXECUTION_CAPABILITY,
    )
    session = FakeSession()
    transaction_ref = f"synthetic-tx://vertical-{run_index}"
    handler = build_playwright_capability_handler(
        plan=_playwright_plan(),
        session_factory=lambda config: session,
        receipt_evidence_writer=lambda receipt: f"browser-receipt://{run_index}/{receipt.action_id}",
        effect_verifier=lambda runtime, receipts: BrowserEffectVerification(
            status=EffectVerificationStatus.VERIFIED_APPLIED,
            evidence_refs=(f"authoritative-readback://stock/{run_index}",),
            transaction_ref=transaction_ref,
        ),
    )
    summary = asyncio.run(
        execute_mission_until_blocked(
            definition=definition,
            checkpoint=new_checkpoint(definition),
            specs=(spec,),
            gateway=EngineGateway([]),
            reasoning_evidence_writer=lambda receipt: "unused",
            capability_handlers={EXECUTION_CAPABILITY: handler},
            authorization_checker=build_mission_command_authorization_checker((authorization,)),
        )
    )
    return definition, spec, authorization, summary, transaction_ref, session


def test_command_browser_effect_checkpoint_two_runs_qualify_and_fresh_third_command_preflights():
    candidate = _candidate()
    foundation = _read_foundation()
    demonstrations = []

    for run_index in (1, 2):
        definition, spec, authorization, summary, tx, session = _execute_verified_browser_mission(run_index)
        assert summary.checkpoint.status is MissionStatus.COMPLETED
        assert session.actions == ["barcode", "quantity", "submit"]
        assert session.closed is True
        demonstrations.append(
            create_write_demonstration_from_completed_mission(
                candidate=candidate,
                definition=definition,
                summary=summary,
                spec=spec,
                authorization=authorization,
                observed_at=NOW + timedelta(minutes=run_index),
                observed_environment_fingerprint=ENV,
                transaction_ref=tx,
                demonstration_id=f"vertical-demo-{run_index}",
            )
        )

    qualified = compile_qualified_write_capability(
        candidate=candidate,
        read_foundation=foundation,
        demonstrations=demonstrations,
    )
    fresh = _authorization(3)
    preflight = preflight_qualified_write_replay(
        capability=qualified,
        authorization=fresh,
        observed_environment_fingerprint=ENV,
        expected_idempotency_key=fresh.idempotency_key,
    )

    assert qualified.status is WriteQualificationStatus.QUALIFIED
    assert qualified.deterministic_replay_allowed is True
    assert preflight.allowed is True
    assert preflight.effect_verification_required is True
    assert preflight.authorization_evidence_ref == fresh.authorization_evidence_ref


def test_completed_mission_trace_without_transaction_evidence_cannot_train_procedure():
    candidate = _candidate()
    definition, spec, authorization, summary, tx, _ = _execute_verified_browser_mission(4)
    step_state = summary.checkpoint.steps[0]
    stripped_state = step_state.model_copy(
        update={"evidence_refs": tuple(ref for ref in step_state.evidence_refs if ref != tx)}
    )
    stripped_checkpoint = summary.checkpoint.model_copy(update={"steps": (stripped_state,)})
    stripped_summary = summary.model_copy(update={"checkpoint": stripped_checkpoint})

    with pytest.raises(ValueError, match="write_qualification_mission_transaction_not_in_checkpoint"):
        create_write_demonstration_from_completed_mission(
            candidate=candidate,
            definition=definition,
            summary=stripped_summary,
            spec=spec,
            authorization=authorization,
            observed_at=NOW + timedelta(minutes=4),
            observed_environment_fingerprint=ENV,
            transaction_ref=tx,
            demonstration_id="vertical-demo-stripped",
        )


def test_wrong_capability_or_permission_trace_cannot_train_candidate():
    candidate = _candidate()
    definition, spec, authorization, summary, tx, _ = _execute_verified_browser_mission(5)
    wrong_spec = spec.model_copy(update={"capability_ref": "synthetic.inventory.delete"})

    with pytest.raises(ValueError, match="write_qualification_mission_capability_mismatch"):
        create_write_demonstration_from_completed_mission(
            candidate=candidate,
            definition=definition,
            summary=summary,
            spec=wrong_spec,
            authorization=authorization,
            observed_at=NOW + timedelta(minutes=5),
            observed_environment_fingerprint=ENV,
            transaction_ref=tx,
            demonstration_id="vertical-demo-wrong-capability",
        )

    wrong_definition = definition.model_copy(
        update={
            "steps": (
                definition.steps[0].model_copy(update={"required_permission": "inventory.admin"}),
            )
        }
    )
    with pytest.raises(ValueError, match="write_qualification_mission_permission_mismatch"):
        create_write_demonstration_from_completed_mission(
            candidate=candidate,
            definition=wrong_definition,
            summary=summary,
            spec=spec,
            authorization=authorization,
            observed_at=NOW + timedelta(minutes=5),
            observed_environment_fingerprint=ENV,
            transaction_ref=tx,
            demonstration_id="vertical-demo-wrong-permission",
        )
