"""Master 38: tenant-bound proactive recommendations with approval authority.

This layer detects/explains governed signals. It never grants itself execution
authority; all proposed actions remain recommendation-only and must traverse the
existing Jarvis/workflow approval and audit chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Risk = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class GovernedSignal:
    tenant_id: str
    key: str
    module: str
    reason: str
    evidence_refs: tuple[str, ...]
    risk: Risk
    policy_version: str
    proposed_action: str | None = None
    recommendation_only: Literal[True] = True


def create_signal(
    *,
    tenant_id: str,
    key: str,
    module: str,
    reason: str,
    evidence_refs: tuple[str, ...],
    risk: Risk,
    policy_version: str,
    proposed_action: str | None = None,
) -> GovernedSignal:
    if not tenant_id.strip():
        raise ValueError("proactive signal tenant is required")
    if not key.strip() or not module.strip():
        raise ValueError("proactive signal identity is required")
    if not evidence_refs or any(not reference.strip() for reference in evidence_refs):
        raise ValueError("proactive signal requires governed evidence")
    if not reason.strip():
        raise ValueError("signal reason required")
    if not policy_version.strip():
        raise ValueError("signal policy version required")
    if proposed_action is not None and not proposed_action.strip():
        raise ValueError("proposed action must be meaningful")

    return GovernedSignal(
        tenant_id=tenant_id,
        key=key,
        module=module,
        reason=reason,
        evidence_refs=evidence_refs,
        risk=risk,
        policy_version=policy_version,
        proposed_action=proposed_action,
    )


def action_requires_approval(signal: GovernedSignal) -> bool:
    return signal.proposed_action is not None


def auto_action_permitted(signal: GovernedSignal) -> bool:
    """Master 38 is proactive intelligence, not a second execution authority."""

    return False
