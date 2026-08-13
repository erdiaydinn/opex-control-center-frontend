from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.ai_orders_v2_manual_policy_promotion import (
    ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    OrdersV2ManualPolicyPromotionProposal,
    _target_policy_review_fingerprint,
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


def test_transition_guard_rejects_replayed_proposal() -> None:
    proposal = _proposal()

    with pytest.raises(ValueError, match="replay"):
        build_orders_v2_policy_transition_guard(
            proposal=proposal,
            evaluated_at=proposal.proposed_at + timedelta(hours=1),
            consumed_proposal_fingerprints=(proposal.proposal_fingerprint,),
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


def test_transition_guard_rejects_malformed_consumed_registry_entry() -> None:
    proposal = _proposal()

    with pytest.raises(ValueError, match="must be sha256"):
        build_orders_v2_policy_transition_guard(
            proposal=proposal,
            evaluated_at=proposal.proposed_at + timedelta(hours=1),
            consumed_proposal_fingerprints=("not-a-sha",),
        )
