import asyncio

import pytest

from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
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


class FakeSession:
    def __init__(self, *, auth_context_ref="auth://corporate-session", fail_action_id=None):
        self.auth_context_ref = auth_context_ref
        self.fail_action_id = fail_action_id
        self.goto_calls = []
        self.actions = []
        self.closed = False

    def goto(self, url):
        self.goto_calls.append(url)

    def perform(self, action):
        self.actions.append(action.action_id)
        if action.action_id == self.fail_action_id:
            raise RuntimeError("synthetic_browser_failure")
        return BrowserActionReceipt(
            action_id=action.action_id,
            application_id="synthetic-portal",
            tenant_scope_ref="tenant://YS_TR",
            auth_context_ref=self.auth_context_ref,
            locator_kind=action.locator.kind,
            action_kind=action.kind,
            completed=True,
            page_url_after="https://portal.example.com/inventory",
        )

    def close(self):
        self.closed = True


def _config():
    return PlaywrightSessionConfig(
        application_id="synthetic-portal",
        tenant_scope_ref="tenant://YS_TR",
        auth_context_ref="auth://corporate-session",
        allowed_hosts=frozenset({"portal.example.com"}),
    )


def _plan():
    return PlaywrightCapabilityPlan(
        capability_ref="synthetic.inventory.adjust",
        session_config=_config(),
        start_url="https://portal.example.com/inventory",
        actions=(
            BrowserAction(
                action_id="barcode",
                kind=BrowserActionKind.FILL,
                locator=BrowserLocator(kind=LocatorKind.LABEL, value="Barcode"),
                input_value="8690000000001",
            ),
            BrowserAction(
                action_id="submit",
                kind=BrowserActionKind.CLICK,
                locator=BrowserLocator(
                    kind=LocatorKind.ROLE,
                    value="button",
                    accessible_name="Save adjustment",
                ),
            ),
        ),
        commit_action_id="submit",
    )


def _mission_step():
    definition = MissionDefinition(
        mission_id="browser-adjust",
        objective="Apply one bounded browser inventory adjustment",
        tenant_id="YS_TR",
        steps=(
            MissionStep(
                step_id="adjust",
                description="Synthetic browser stock adjustment",
                side_effect=True,
                required_permission="inventory.adjust",
                idempotency_key="idem-1",
                effect_verifier_ref="synthetic://inventory/read-back",
            ),
        ),
    )
    checkpoint = new_checkpoint(definition)
    return definition, definition.steps[0], checkpoint.steps[0]


def _writer(receipt):
    return f"browser-receipt://{receipt.application_id}/{receipt.action_id}"


def test_verified_applied_browser_workflow_returns_effect_verified_success():
    session = FakeSession()
    handler = build_playwright_capability_handler(
        plan=_plan(),
        session_factory=lambda config: session,
        receipt_evidence_writer=_writer,
        effect_verifier=lambda runtime, receipts: BrowserEffectVerification(
            status=EffectVerificationStatus.VERIFIED_APPLIED,
            evidence_refs=("authoritative-readback://stock/7",),
            transaction_ref="portal-tx://123",
        ),
    )
    definition, step, state = _mission_step()

    outcome = asyncio.run(handler(definition, step, state, step.idempotency_key))

    assert outcome.succeeded is True
    assert outcome.effect_verified is True
    assert outcome.ambiguous_outcome is False
    assert outcome.transaction_ref == "portal-tx://123"
    assert "browser-receipt://synthetic-portal/submit" in outcome.evidence_refs
    assert "authoritative-readback://stock/7" in outcome.evidence_refs
    assert session.actions == ["barcode", "submit"]
    assert session.closed is True


def test_unknown_authoritative_effect_halts_upstream_as_ambiguous():
    session = FakeSession()
    handler = build_playwright_capability_handler(
        plan=_plan(),
        session_factory=lambda config: session,
        receipt_evidence_writer=_writer,
        effect_verifier=lambda runtime, receipts: BrowserEffectVerification(
            status=EffectVerificationStatus.UNKNOWN,
            evidence_refs=("readback-attempt://timeout",),
            error_code="authoritative_readback_timeout",
        ),
    )
    definition, step, state = _mission_step()

    outcome = asyncio.run(handler(definition, step, state, step.idempotency_key))

    assert outcome.succeeded is False
    assert outcome.effect_verified is False
    assert outcome.ambiguous_outcome is True
    assert outcome.error_code == "authoritative_readback_timeout"
    assert session.closed is True


def test_exception_on_commit_action_is_ambiguous_not_safe_retry():
    session = FakeSession(fail_action_id="submit")
    handler = build_playwright_capability_handler(
        plan=_plan(),
        session_factory=lambda config: session,
        receipt_evidence_writer=_writer,
        effect_verifier=lambda runtime, receipts: pytest.fail("verifier must not run after commit exception"),
    )
    definition, step, state = _mission_step()

    outcome = asyncio.run(handler(definition, step, state, step.idempotency_key))

    assert outcome.succeeded is False
    assert outcome.ambiguous_outcome is True
    assert outcome.error_code == "browser_error_after_commit_boundary:RuntimeError"
    assert session.closed is True


def test_exception_before_commit_is_nonambiguous_failure():
    session = FakeSession(fail_action_id="barcode")
    handler = build_playwright_capability_handler(
        plan=_plan(),
        session_factory=lambda config: session,
        receipt_evidence_writer=_writer,
        effect_verifier=lambda runtime, receipts: pytest.fail("verifier must not run before commit"),
    )
    definition, step, state = _mission_step()

    outcome = asyncio.run(handler(definition, step, state, step.idempotency_key))

    assert outcome.succeeded is False
    assert outcome.ambiguous_outcome is False
    assert outcome.error_code == "browser_error_before_commit_boundary:RuntimeError"
    assert session.closed is True


def test_browser_capability_start_url_must_be_exact_allowlisted_https():
    with pytest.raises(ValueError, match="playwright_capability_start_url_not_allowlisted_https"):
        PlaywrightCapabilityPlan(
            capability_ref="bad",
            session_config=_config(),
            start_url="https://evil.example.com/inventory",
            actions=_plan().actions,
            commit_action_id="submit",
        )
