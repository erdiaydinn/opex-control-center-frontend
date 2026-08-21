from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_live_cross_tenant_evidence import sha256_text
from app.core.ai_orders_v2_manual_policy_promotion import (
    ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    OrdersV2ManualPolicyPromotionProposal,
    _target_policy_review_fingerprint,
)
from app.core.ai_orders_v2_policy_consumption_commit_attestation import (
    COMMIT_ATTESTATION_BLOCKER,
    attest_orders_v2_policy_consumption_commit_candidate,
)
from app.core.ai_orders_v2_policy_consumption_ledger import (
    LEDGER_GENESIS_FINGERPRINT,
    OrdersV2PolicyConsumptionEntry,
    OrdersV2PolicyConsumptionLedger,
    build_next_orders_v2_policy_consumption_entry,
    get_orders_v2_policy_consumption_ledger,
)
from app.core.ai_orders_v2_policy_consumption_patch import (
    CONSUMPTION_PATCH_BLOCKER,
    OrdersV2PolicyConsumptionPatchArtifact,
    build_orders_v2_policy_consumption_patch_candidate,
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


def _guard(proposal: OrdersV2ManualPolicyPromotionProposal):
    return build_orders_v2_policy_transition_guard(
        proposal=proposal,
        evaluated_at=proposal.proposed_at + timedelta(hours=1),
    )


def _review():
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = _guard(proposal)
    review = build_orders_v2_policy_consumption_review_proposal(
        ledger=ledger,
        proposal=proposal,
        guard=guard,
        reviewer_identity="reviewer@example.invalid",
        reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
    )
    return ledger, proposal, guard, review


def test_consumption_review_binds_exact_ledger_proposal_and_guard() -> None:
    ledger, proposal, guard, review = _review()

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
    guard = _guard(proposal)
    drifted = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(
            OrdersV2PolicyConsumptionEntry(
                sequence=1,
                consumed_at=proposal.proposed_at,
                proposal_fingerprint="1" * 64,
                guard_fingerprint="2" * 64,
                previous_entry_fingerprint=LEDGER_GENESIS_FINGERPRINT,
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
    guard = _guard(proposal)
    substituted = guard.model_copy(update={"proposal_fingerprint": "f" * 64})

    with pytest.raises(ValueError, match="not bound"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=ledger,
            proposal=proposal,
            guard=substituted,
            reviewer_identity="reviewer@example.invalid",
            reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
        )


def test_consumption_review_rejects_naive_or_early_timestamp() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = _guard(proposal)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=ledger,
            proposal=proposal,
            guard=guard,
            reviewer_identity="reviewer@example.invalid",
            reviewed_at=datetime(2026, 8, 13, 13, 5),
        )

    with pytest.raises(ValueError, match="transition guard"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=ledger,
            proposal=proposal,
            guard=guard,
            reviewer_identity="reviewer@example.invalid",
            reviewed_at=guard.evaluated_at - timedelta(seconds=1),
        )


def test_consumption_review_rejects_policy_promoter_as_reviewer() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    raw_identity = "same-person@example.invalid"
    proposal = _proposal().model_copy(
        update={"policy_promoter_identity_sha256": sha256_text(raw_identity)}
    )
    guard = _guard(proposal)

    with pytest.raises(ValueError, match="independent"):
        build_orders_v2_policy_consumption_review_proposal(
            ledger=ledger,
            proposal=proposal,
            guard=guard,
            reviewer_identity=raw_identity,
            reviewed_at=guard.evaluated_at + timedelta(minutes=5),
        )


def test_consumption_review_rejects_tamper_and_hides_raw_identity() -> None:
    ledger = get_orders_v2_policy_consumption_ledger()
    proposal = _proposal()
    guard = _guard(proposal)
    raw_identity = "security-reviewer@example.invalid"
    review = build_orders_v2_policy_consumption_review_proposal(
        ledger=ledger,
        proposal=proposal,
        guard=guard,
        reviewer_identity=raw_identity,
        reviewed_at=proposal.proposed_at + timedelta(hours=1, minutes=5),
    )

    payload = review.model_dump(mode="python")
    payload["ledger_mutation_permitted"] = True
    with pytest.raises(ValidationError):
        OrdersV2PolicyConsumptionReviewProposal.model_validate(payload)

    assert raw_identity not in review.model_dump_json()


def test_consumption_patch_binds_review_to_exact_next_ledger_state() -> None:
    ledger, _, _, review = _review()
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


def test_consumption_patch_rejects_entry_sequence_and_mutation_tamper() -> None:
    ledger, _, _, review = _review()

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

    patch = build_orders_v2_policy_consumption_patch_candidate(
        ledger=ledger,
        review=review,
    )
    payload = patch.model_dump(mode="python")
    payload["ledger_mutation_permitted"] = True
    with pytest.raises(ValidationError):
        OrdersV2PolicyConsumptionPatchArtifact.model_validate(payload)


def test_consumption_commit_attestation_binds_exact_patch_and_append() -> None:
    ledger, _, _, review = _review()
    patch = build_orders_v2_policy_consumption_patch_candidate(
        ledger=ledger,
        review=review,
    )
    entry = build_next_orders_v2_policy_consumption_entry(
        ledger=ledger,
        proposal_fingerprint=review.proposal_fingerprint,
        guard_fingerprint=review.guard_fingerprint,
        consumed_at=review.reviewed_at,
    )
    candidate = OrdersV2PolicyConsumptionLedger(
        version=ledger.version,
        kind=ledger.kind,
        entries=(*ledger.entries, entry),
    )

    attestation = attest_orders_v2_policy_consumption_commit_candidate(
        previous_ledger=ledger,
        candidate_ledger=candidate,
        patch=patch,
    )

    assert attestation.patch_fingerprint == patch.patch_fingerprint
    assert attestation.previous_ledger_fingerprint == ledger.ledger_fingerprint
    assert attestation.resulting_ledger_fingerprint == candidate.ledger_fingerprint
    assert attestation.appended_entry_fingerprint == entry.entry_fingerprint
    assert attestation.commit_candidate_validated is True
    assert attestation.human_merge_required is True
    assert attestation.ledger_mutation_permitted is False
    assert attestation.policy_mutation_permitted is False
    assert attestation.execution_enable_permitted is False
    assert attestation.production_ready is False
    assert attestation.production_blocker == COMMIT_ATTESTATION_BLOCKER


def test_consumption_commit_attestation_rejects_extra_append() -> None:
    ledger, _, _, review = _review()
    patch = build_orders_v2_policy_consumption_patch_candidate(
        ledger=ledger,
        review=review,
    )
    first = build_next_orders_v2_policy_consumption_entry(
        ledger=ledger,
        proposal_fingerprint=review.proposal_fingerprint,
        guard_fingerprint=review.guard_fingerprint,
        consumed_at=review.reviewed_at,
    )
    one_entry_ledger = OrdersV2PolicyConsumptionLedger(
        version=ledger.version,
        kind=ledger.kind,
        entries=(first,),
    )
    second = build_next_orders_v2_policy_consumption_entry(
        ledger=one_entry_ledger,
        proposal_fingerprint="f" * 64,
        guard_fingerprint="e" * 64,
        consumed_at=review.reviewed_at + timedelta(minutes=1),
    )
    candidate = OrdersV2PolicyConsumptionLedger(
        version=ledger.version,
        kind=ledger.kind,
        entries=(first, second),
    )
    patched = patch.model_copy(
        update={"resulting_ledger_fingerprint": candidate.ledger_fingerprint}
    )

    with pytest.raises(ValueError, match="exactly one appended entry"):
        attest_orders_v2_policy_consumption_commit_candidate(
            previous_ledger=ledger,
            candidate_ledger=candidate,
            patch=patched,
        )
