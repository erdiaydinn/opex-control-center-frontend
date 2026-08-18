"""Mission-capability adapter for the managed Playwright runtime.

The adapter turns a bounded browser workflow into an EAY mission capability.
It never equates a successful click/toast with a successful business effect.
After the configured commit action it requires an independent effect verifier:
- VERIFIED_APPLIED -> success + effect evidence
- VERIFIED_NOT_APPLIED -> safe failure/retry may be possible
- UNKNOWN -> ambiguous write outcome, so the durable mission halts

Any exception during or after the commit action is treated conservatively as
ambiguous because the remote system may already have accepted the write.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .mission_execution import CapabilityExecutionOutcome, CapabilityHandler
from .mission_runtime import MissionDefinition, MissionStep, StepCheckpoint
from .playwright_computer_runtime import (
    BrowserAction,
    BrowserActionReceipt,
    ManagedPlaywrightSession,
    PlaywrightSessionConfig,
)

PLAYWRIGHT_MISSION_ADAPTER_CONTRACT = "eay-playwright-mission-adapter-v1"


class EffectVerificationStatus(str, Enum):
    VERIFIED_APPLIED = "verified_applied"
    VERIFIED_NOT_APPLIED = "verified_not_applied"
    UNKNOWN = "unknown"


class BrowserEffectVerification(BaseModel):
    contract: str = PLAYWRIGHT_MISSION_ADAPTER_CONTRACT
    status: EffectVerificationStatus
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    transaction_ref: str | None = None
    error_code: str | None = None


class PlaywrightCapabilityPlan(BaseModel):
    contract: str = PLAYWRIGHT_MISSION_ADAPTER_CONTRACT
    capability_ref: str = Field(min_length=1)
    session_config: PlaywrightSessionConfig
    start_url: str = Field(min_length=8)
    actions: tuple[BrowserAction, ...] = Field(min_length=1)
    commit_action_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def workflow_is_bounded_and_allowlisted(self) -> "PlaywrightCapabilityPlan":
        action_ids = [item.action_id for item in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("playwright_capability_action_ids_must_be_unique")
        if self.commit_action_id not in set(action_ids):
            raise ValueError("playwright_capability_commit_action_missing")
        parsed = urlparse(self.start_url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme != "https" or host not in self.session_config.allowed_hosts:
            raise ValueError("playwright_capability_start_url_not_allowlisted_https")
        return self


SessionFactory = Callable[[PlaywrightSessionConfig], ManagedPlaywrightSession]
ReceiptEvidenceWriter = Callable[[BrowserActionReceipt], str]
EffectVerifier = Callable[
    [ManagedPlaywrightSession, tuple[BrowserActionReceipt, ...]],
    BrowserEffectVerification,
]


def build_playwright_capability_handler(
    *,
    plan: PlaywrightCapabilityPlan,
    session_factory: SessionFactory,
    receipt_evidence_writer: ReceiptEvidenceWriter,
    effect_verifier: EffectVerifier,
) -> CapabilityHandler:
    """Build an async mission handler around a synchronous managed session."""

    def execute_sync(
        definition: MissionDefinition,
        step: MissionStep,
        state: StepCheckpoint,
        idempotency_key: str,
    ) -> CapabilityExecutionOutcome:
        if step.side_effect and not idempotency_key:
            raise ValueError("playwright_mission_side_effect_requires_idempotency_key")
        if step.effect_verifier_ref is None:
            raise ValueError("playwright_mission_requires_effect_verifier_ref")

        session = session_factory(plan.session_config)
        receipts: list[BrowserActionReceipt] = []
        evidence_refs: list[str] = []
        commit_reached = False
        try:
            try:
                session.goto(plan.start_url)
                for action in plan.actions:
                    if action.action_id == plan.commit_action_id:
                        commit_reached = True
                    receipt = session.perform(action)
                    receipts.append(receipt)
                    evidence_ref = receipt_evidence_writer(receipt)
                    if not evidence_ref.strip():
                        raise ValueError("playwright_receipt_evidence_writer_returned_empty_ref")
                    evidence_refs.append(evidence_ref)
            except Exception as exc:
                if commit_reached:
                    return CapabilityExecutionOutcome(
                        succeeded=False,
                        ambiguous_outcome=True,
                        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
                        error_code=f"browser_error_after_commit_boundary:{type(exc).__name__}",
                    )
                return CapabilityExecutionOutcome(
                    succeeded=False,
                    ambiguous_outcome=False,
                    evidence_refs=tuple(dict.fromkeys(evidence_refs)),
                    error_code=f"browser_error_before_commit_boundary:{type(exc).__name__}",
                )

            verification = effect_verifier(session, tuple(receipts))
            combined_evidence = tuple(
                dict.fromkeys((*evidence_refs, *verification.evidence_refs))
            )
            if verification.status is EffectVerificationStatus.VERIFIED_APPLIED:
                return CapabilityExecutionOutcome(
                    succeeded=True,
                    effect_verified=True,
                    evidence_refs=combined_evidence,
                    transaction_ref=verification.transaction_ref,
                )
            if verification.status is EffectVerificationStatus.VERIFIED_NOT_APPLIED:
                return CapabilityExecutionOutcome(
                    succeeded=False,
                    effect_verified=False,
                    ambiguous_outcome=False,
                    evidence_refs=combined_evidence,
                    transaction_ref=verification.transaction_ref,
                    error_code=verification.error_code or "authoritative_effect_not_applied",
                )
            return CapabilityExecutionOutcome(
                succeeded=False,
                effect_verified=False,
                ambiguous_outcome=True,
                evidence_refs=combined_evidence,
                transaction_ref=verification.transaction_ref,
                error_code=verification.error_code or "authoritative_effect_unknown",
            )
        finally:
            try:
                session.close()
            except Exception:
                pass

    async def handler(
        definition: MissionDefinition,
        step: MissionStep,
        state: StepCheckpoint,
        idempotency_key: str,
    ) -> CapabilityExecutionOutcome:
        return await asyncio.to_thread(
            execute_sync,
            definition,
            step,
            state,
            idempotency_key,
        )

    return handler
