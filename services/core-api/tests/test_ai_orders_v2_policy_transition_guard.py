from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

import app.core.ai_orders_v2_policy_transition_guard as transition_guard
from app.core.ai_orders_v2_manual_policy_promotion import (
    ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    OrdersV2ManualPolicyPromotionProposal,
    _target_policy_review_fingerprint,
)
from app.core.ai_orders_v2_policy_consumption_ledger import (
    LEDGER_GENESIS_FINGERPRINT,
    OrdersV2PolicyConsumptionEntry,
    OrdersV2PolicyConsumptionLedger,
    build_next_orders_v2_policy_consumption_entry,
    get_orders_v2_policy_consumption_ledger,
)
from app.core.ai_orders_v2_policy_transition_guard import (
    ORDERS_V2_POLICY_TRANSITION_BLOCKER,
    build_orders_v2_policy_transition_guard,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    ai_query_contract_policy_fingerprint,
)


def _proposal(
    *,
    proposed_at: datetime = datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
) -> OrdersV2ManualPolicyPromotionProposal:
    current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    return OrdersV2ManualPolicyPromotionProposal(
        version=1,
        kind="orders_v2_manual_policy_promotion_proposal",
        environment="production",
        proposed_at=proposed_at,
        proposal_manifest_sha256="a" * 64,
        policy_promoter_identity_sha256="b" * 64,
        human_review_fingerprint="c" * 64,
        release_gate_fingerprint="d" * 64,
        deployment_authorization_fingerprint="e" * 64,
        current_policy_fingerprint=ai_query_contract_policy_fingerprint(current),
        target_contract_id="ops.kpi.orders.v2",
        target_contract_revision=2,
        target_data_scope_argument="stores",
        target_tenant_discriminator_parameter="entity_ids",
        target_query_template_sha256=ORDERS_V2_CANDIDATE.template_fingerprint,
        target_review_fingerprint=_target_policy_review_fingerprint(),
        proposal_decision="APPROVE_FOR_MANUAL_VERSION_CONTROL_CHANGE",
        manual_version_control_change_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    )


def test_transition_guard_passes_only_as_non_mutating_evidence() -> None:
    proposal = _proposal()
    artifact = build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )

    assert artifact.transition_guard_passed is True
    assert artifact.drift_detected is False
    assert artifact.replay_detected is False
    assert artifact.expired is False
    assert artifact.proposal_age_seconds == 3600
    assert artifact.proposal_max_age_seconds == 21600
    assert artifact.consumption_ledger_fingerprint == (
        get_orders_v2_policy_consumption_ledger().ledger_fingerprint
    )
    assert artifact.policy_mutation_permitted is False
    assert artifact.execution_enable_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert artifact.production_blocker == ORDERS_V2_POLICY_TRANSITION_BLOCKER
    assert len(artifact.guard_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False


def test_transition_guard_rejects_expired_proposal() -> None:
    proposal = _proposal()

    with pytest.raises(ValueError, match="expired"):
        build_orders_v2_policy_transition_guard(
            proposal=proposal,
            evaluated_at=proposal.proposed_at + timedelta(hours=6, seconds=1),
        )


def test_transition_guard_rejects_replay_from_canonical_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    canonical = get_orders_v2_policy_consumption_ledger()
    entry = build_next_orders_v2_policy_consumption_entry(
        ledger=canonical,
        proposal_fingerprint=proposal.proposal_fingerprint,
        guard_fingerprint="f" * 64,
        consumed_at=proposal.proposed_at + timedelta(hours=1),
    )
    consumed = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(entry,),
    )
    monkeypatch.setattr(
        transition_guard,
        "get_orders_v2_policy_consumption_ledger",
        lambda: consumed,
    )

    with pytest.raises(ValueError, match="replay"):
        build_orders_v2_policy_transition_guard(
            proposal=proposal,
            evaluated_at=proposal.proposed_at + timedelta(hours=2),
        )


def test_consumption_ledger_is_hash_chained_and_rejects_tamper() -> None:
    proposal = _proposal()
    canonical = get_orders_v2_policy_consumption_ledger()
    assert canonical.entries == ()
    assert len(canonical.ledger_fingerprint) == 64

    first = build_next_orders_v2_policy_consumption_entry(
        ledger=canonical,
        proposal_fingerprint=proposal.proposal_fingerprint,
        guard_fingerprint="1" * 64,
        consumed_at=proposal.proposed_at + timedelta(hours=1),
    )
    assert first.sequence == 1
    assert first.previous_entry_fingerprint == LEDGER_GENESIS_FINGERPRINT

    with pytest.raises(ValidationError, match="hash chain"):
        OrdersV2PolicyConsumptionLedger(
            version=1,
            kind="orders_v2_policy_consumption_ledger",
            entries=(
                OrdersV2PolicyConsumptionEntry(
                    sequence=1,
                    consumed_at=first.consumed_at,
                    proposal_fingerprint=first.proposal_fingerprint,
                    guard_fingerprint=first.guard_fingerprint,
                    previous_entry_fingerprint="0" * 64,
                ),
            ),
        )


def test_transition_guard_rejects_policy_drift() -> None:
    proposal = _proposal()
    stale = proposal.model_copy(
        update={"current_policy_fingerprint": "f" * 64}
    )

    with pytest.raises(ValueError, match="drift"):
        build_orders_v2_policy_transition_guard(
            proposal=stale,
            evaluated_at=proposal.proposed_at + timedelta(hours=1),
        )


def test_transition_guard_rejects_future_proposal() -> None:
    proposal = _proposal()

    with pytest.raises(ValueError, match="cannot precede"):
        build_orders_v2_policy_transition_guard(
            proposal=proposal,
            evaluated_at=proposal.proposed_at - timedelta(seconds=1),
        )
