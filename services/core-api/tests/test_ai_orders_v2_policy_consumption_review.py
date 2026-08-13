from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_manual_policy_promotion import (
    ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    OrdersV2ManualPolicyPromotionProposal,
    _target_policy_review_fingerprint,
)
from app.core.ai_orders_v2_policy_consumption_ledger import (
    OrdersV2PolicyConsumptionEntry,
    OrdersV2PolicyConsumptionLedger,
    get_orders_v2_policy_consumption_ledger,
)
from app.core.ai_orders_v2_policy_consumption_review import (
    CONSUMPTION_REVIEW_BLOCKER,
    OrdersV2PolicyConsumptionReviewProposal,
    build_orders_v2_policy_consumption_review_proposal,
)
from app.core.ai_orders_v2_policy_transition_guard import (
    build_orders_v2_policy_transition_guard,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    ai_query_contract_policy_fingerprint,
)


def _proposal() -> OrdersV2ManualPolicyPromotionProposal:
    current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    return OrdersV2ManualPolicyPromotionProposal(
        version=1,
        kind="orders_v2_manual_policy_promotion_proposal",
        environment="production",
        proposed_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
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


def test_consumption_review_binds_exact_ledger_proposal_and_guard() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )
    review = build_orders_v2_policy_consumption_review_proposal(
        ledger=ledger,
        proposal=proposal,
        guard=guard,
        reviewer_identity="reviewer@example.invalid",
        reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
    )

    assert review.current_ledger_fingerprint == ledger.ledger_fingerprint
    assert review.proposal_fingerprint == proposal.proposal_fingerprint
    assert review.guard_fingerprint == guard.guard_fingerprint
    assert review.proposed_entry_sequence == 1
    assert review.version_controlled_ledger_append_required is True
    assert review.ledger_mutation_permitted is False
    assert review.policy_mutation_permitted is False
    assert review.execution_enable_permitted is False
    assert review.promotion_eligible is False
    assert review.production_ready is False
    assert review.production_blocker == CONSUMPTION_REVIEW_BLOCKER
    assert len(review.proposed_entry_fingerprint) == 64
    assert len(review.review_fingerprint) == 64
    assert ledger.entries == ()


def test_consumption_review_rejects_ledger_drift() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )
    drifted = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(
            OrdersV2PolicyConsumptionEntry(
                sequence=1,
                consumed_at=proposal.proposed_at,
                proposal_fingerprint="1" * 64,
                guard_fingerprint="2" * 64,
                previous_entry_fingerprint=(
                    __import__(
                        "app.core.ai_orders_v2_policy_consumption_ledger",
                        fromlist=["LEDGER_GENESIS_FINGERPRINT"],
                    ).LEDGER_GENESIS_FINGERPRINT
                ),
            ),
        ),
    )

    assert drifted.ledger_fingerprint != ledger.ledger_fingerprint
    with pytest.raises(ValueError, match="ledger drift"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=drifted,
            proposal=proposal,
            guard=guard,
            reviewer_identity="reviewer@example.invalid",
            reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
        )


def test_consumption_review_rejects_guard_substitution() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )
    substituted = guard.model_copy(update={"proposal_fingerprint": "f" * 64})

    with pytest.raises(ValueError, match="not bound"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=ledger,
            proposal=proposal,
            guard=substituted,
            reviewer_identity="reviewer@example.invalid",
            reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
        )


def test_consumption_review_rejects_naive_timestamp_and_tamper() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=ledger,
            proposal=proposal,
            guard=guard,
            reviewer_identity="reviewer@example.invalid",
            reviewed_at=datetime(2026, 8, 13, 13, 5),
        )

    review = build_orders_v2_policy_consumption_review_proposal(
        ledger=ledger,
        proposal=proposal,
        guard=guard,
        reviewer_identity="reviewer@example.invalid",
        reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
    )
    payload = review.model_dump(mode="python")
    payload["ledger_mutation_permitted"] = True
    with pytest.raises(ValidationError):
        OrdersV2PolicyConsumptionReviewProposal.model_validate(payload)


def test_consumption_review_does_not_store_raw_reviewer_identity() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )
    raw_identity = "security-reviewer@example.invalid"
    review = build_orders_v2_policy_consumption_review_proposal(
        ledger=ledger,
        proposal=proposal,
        guard=guard,
        reviewer_identity=raw_identity,
        reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
    )

    assert raw_identity not in review.model_dump_json()
