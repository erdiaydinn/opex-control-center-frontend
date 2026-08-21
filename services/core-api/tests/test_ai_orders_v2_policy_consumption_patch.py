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
    get_orders_v2_policy_consumption_ledger,
)
from app.core.ai_orders_v2_policy_consumption_patch import (
    CONSUMPTION_PATCH_BLOCKER,
    OrdersV2PolicyConsumptionPatchArtifact,
    build_orders_v2_policy_consumption_patch_candidate,
)
from app.core.ai_orders_v2_policy_consumption_review import (
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


def _review():
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
        reviewer_identity="ledger-reviewer@example.invalid",
        reviewed_at=guard.evaluated_at + timedelta(minutes=5),
    )
    return ledger, review


def test_patch_candidate_binds_review_and_exact_next_ledger_state() -> None:
    ledger, review = _review()
    patch = build_orders_v2_policy_consumption_patch_candidate(
        ledger=ledger,
        review=review,
    )

    assert patch.review_fingerprint == review.review_fingerprint
    assert patch.current_ledger_fingerprint == ledger.ledger_fingerprint
    assert patch.proposed_entry_fingerprint == review.proposed_entry_fingerprint
    assert patch.expected_next_sequence == 1
    assert patch.resulting_ledger_fingerprint != ledger.ledger_fingerprint
    assert patch.append_validation_passed is True
    assert patch.manual_version_control_commit_required is True
    assert patch.ledger_mutation_permitted is False
    assert patch.policy_mutation_permitted is False
    assert patch.execution_enable_permitted is False
    assert patch.promotion_eligible is False
    assert patch.production_ready is False
    assert patch.production_blocker == CONSUMPTION_PATCH_BLOCKER
    assert len(patch.patch_fingerprint) == 64
    assert ledger.entries == ()


def test_patch_candidate_rejects_review_entry_or_sequence_substitution() -> None:
    ledger, review = _review()

    with pytest.raises(ValueError, match="entry fingerprint"):
        build_orders_v2_policy_consumption_patch_candidate(
            ledger=ledger,
            review=review.model_copy(
                update={"proposed_entry_fingerprint": "f" * 64}
            ),
        )

    with pytest.raises(ValueError, match="sequence mismatch"):
        build_orders_v2_policy_consumption_patch_candidate(
            ledger=ledger,
            review=review.model_copy(update={"proposed_entry_sequence": 2}),
        )


def test_patch_artifact_rejects_mutation_tamper() -> None:
    ledger, review = _review()
    patch = build_orders_v2_policy_consumption_patch_candidate(
        ledger=ledger,
        review=review,
    )
    payload = patch.model_dump(mode="python")
    payload["ledger_mutation_permitted"] = True
    with pytest.raises(ValidationError):
        OrdersV2PolicyConsumptionPatchArtifact.model_validate(payload)
