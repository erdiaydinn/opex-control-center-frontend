from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.ai_orders_v2_manual_policy_promotion import (
    ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    OrdersV2ManualPolicyPromotionProposal,
    _target_policy_review_fingerprint,
)
from app.core.ai_orders_v2_policy_consumption_proposal import (
    CONSUMPTION_PROPOSAL_BLOCKER,
    build_orders_v2_policy_consumption_proposal,
)
from app.core.ai_orders_v2_policy_transition_guard import (
    build_orders_v2_policy_transition_guard,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    ai_query_contract_policy_fingerprint,
)


def _guard():
    proposed_at = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    proposal = OrdersV2ManualPolicyPromotionProposal(
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
    return build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposed_at + timedelta(hours=1),
    )


def test_consumption_proposal_binds_guard_and_ledger_without_mutation() -> None:
    guard = _guard()
    artifact = build_orders_v2_policy_consumption_proposal(
        guard=guard,
        proposed_at=guard.evaluated_at + timedelta(minutes=5),
    )
    assert artifact.proposal_fingerprint == guard.proposal_fingerprint
    assert artifact.guard_fingerprint == guard.guard_fingerprint
    assert artifact.current_ledger_fingerprint == guard.consumption_ledger_fingerprint
    assert artifact.proposed_entry_sequence >= 1
    assert len(artifact.proposed_entry_fingerprint) == 64
    assert len(artifact.consumption_proposal_fingerprint) == 64
    assert artifact.ledger_mutation_permitted is False
    assert artifact.policy_mutation_permitted is False
    assert artifact.execution_enable_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert artifact.production_blocker == CONSUMPTION_PROPOSAL_BLOCKER


def test_consumption_proposal_rejects_timestamp_before_guard() -> None:
    guard = _guard()
    with pytest.raises(ValueError, match="cannot precede"):
        build_orders_v2_policy_consumption_proposal(
            guard=guard,
            proposed_at=guard.evaluated_at - timedelta(seconds=1),
        )


def test_consumption_proposal_rejects_ledger_drift() -> None:
    guard = _guard().model_copy(
        update={"consumption_ledger_fingerprint": "f" * 64}
    )
    with pytest.raises(ValueError, match="ledger drift"):
        build_orders_v2_policy_consumption_proposal(
            guard=guard,
            proposed_at=guard.evaluated_at + timedelta(minutes=1),
        )
