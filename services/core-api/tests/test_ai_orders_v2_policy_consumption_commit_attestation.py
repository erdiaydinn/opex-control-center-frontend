from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_policy_consumption_commit_attestation import (
    COMMIT_ATTESTATION_BLOCKER,
    OrdersV2PolicyConsumptionCommitAttestation,
    attest_orders_v2_policy_consumption_commit_candidate,
)
from app.core.ai_orders_v2_policy_consumption_ledger import (
    LEDGER_GENESIS_FINGERPRINT,
    OrdersV2PolicyConsumptionEntry,
    OrdersV2PolicyConsumptionLedger,
)
from app.core.ai_orders_v2_policy_consumption_patch import (
    CONSUMPTION_PATCH_BLOCKER,
    OrdersV2PolicyConsumptionPatchArtifact,
)


def _entry(
    *,
    sequence: int,
    proposal: str,
    guard: str,
    previous: str,
) -> OrdersV2PolicyConsumptionEntry:
    return OrdersV2PolicyConsumptionEntry(
        sequence=sequence,
        consumed_at=datetime(2026, 8, 13, 15, sequence, tzinfo=UTC),
        proposal_fingerprint=proposal,
        guard_fingerprint=guard,
        previous_entry_fingerprint=previous,
    )


def _fixture() -> tuple[
    OrdersV2PolicyConsumptionLedger,
    OrdersV2PolicyConsumptionLedger,
    OrdersV2PolicyConsumptionPatchArtifact,
]:
    previous = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(),
    )
    appended = _entry(
        sequence=1,
        proposal="1" * 64,
        guard="2" * 64,
        previous=LEDGER_GENESIS_FINGERPRINT,
    )
    candidate = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(appended,),
    )
    patch = OrdersV2PolicyConsumptionPatchArtifact(
        version=1,
        kind="orders_v2_policy_consumption_patch_candidate",
        review_fingerprint="3" * 64,
        current_ledger_fingerprint=previous.ledger_fingerprint,
        proposed_entry_fingerprint=appended.entry_fingerprint,
        expected_next_sequence=1,
        resulting_ledger_fingerprint=candidate.ledger_fingerprint,
        append_validation_passed=True,
        manual_version_control_commit_required=True,
        ledger_mutation_permitted=False,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=CONSUMPTION_PATCH_BLOCKER,
    )
    return previous, candidate, patch


def test_commit_attestation_accepts_only_exact_reviewed_single_append() -> None:
    previous, candidate, patch = _fixture()

    attestation = attest_orders_v2_policy_consumption_commit_candidate(
        previous_ledger=previous,
        candidate_ledger=candidate,
        patch=patch,
    )

    assert attestation.patch_fingerprint == patch.patch_fingerprint
    assert attestation.previous_ledger_fingerprint == previous.ledger_fingerprint
    assert attestation.resulting_ledger_fingerprint == candidate.ledger_fingerprint
    assert attestation.appended_entry_fingerprint == candidate.entries[-1].entry_fingerprint
    assert attestation.resulting_entry_count == 1
    assert attestation.commit_candidate_validated is True
    assert attestation.human_merge_required is True
    assert attestation.ledger_mutation_permitted is False
    assert attestation.policy_mutation_permitted is False
    assert attestation.execution_enable_permitted is False
    assert attestation.promotion_eligible is False
    assert attestation.production_ready is False
    assert attestation.production_blocker == COMMIT_ATTESTATION_BLOCKER
    assert len(attestation.attestation_fingerprint) == 64


def test_commit_attestation_rejects_resulting_ledger_mismatch() -> None:
    previous, candidate, patch = _fixture()
    drifted_patch = patch.model_copy(
        update={"resulting_ledger_fingerprint": "f" * 64}
    )

    with pytest.raises(ValueError, match="resulting ledger fingerprint mismatch"):
        attest_orders_v2_policy_consumption_commit_candidate(
            previous_ledger=previous,
            candidate_ledger=candidate,
            patch=drifted_patch,
        )


def test_commit_attestation_rejects_extra_append() -> None:
    previous, candidate, patch = _fixture()
    first = candidate.entries[0]
    second = _entry(
        sequence=2,
        proposal="4" * 64,
        guard="5" * 64,
        previous=first.entry_fingerprint,
    )
    extra = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(first, second),
    )
    patched = patch.model_copy(
        update={"resulting_ledger_fingerprint": extra.ledger_fingerprint}
    )

    with pytest.raises(ValueError, match="exactly one appended entry"):
        attest_orders_v2_policy_consumption_commit_candidate(
            previous_ledger=previous,
            candidate_ledger=extra,
            patch=patched,
        )


def test_commit_attestation_rejects_wrong_sequence_and_entry_fingerprint() -> None:
    previous, candidate, patch = _fixture()

    wrong_sequence = patch.model_copy(update={"expected_next_sequence": 2})
    with pytest.raises(ValueError, match="sequence mismatch"):
        attest_orders_v2_policy_consumption_commit_candidate(
            previous_ledger=previous,
            candidate_ledger=candidate,
            patch=wrong_sequence,
        )

    wrong_entry = patch.model_copy(update={"proposed_entry_fingerprint": "e" * 64})
    with pytest.raises(ValueError, match="entry fingerprint mismatch"):
        attest_orders_v2_policy_consumption_commit_candidate(
            previous_ledger=previous,
            candidate_ledger=candidate,
            patch=wrong_entry,
        )


def test_commit_attestation_rejects_history_rewrite() -> None:
    old = _entry(
        sequence=1,
        proposal="6" * 64,
        guard="7" * 64,
        previous=LEDGER_GENESIS_FINGERPRINT,
    )
    previous = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(old,),
    )
    rewritten = _entry(
        sequence=1,
        proposal="8" * 64,
        guard="9" * 64,
        previous=LEDGER_GENESIS_FINGERPRINT,
    )
    appended = _entry(
        sequence=2,
        proposal="a" * 64,
        guard="b" * 64,
        previous=rewritten.entry_fingerprint,
    )
    candidate = OrdersV2PolicyConsumptionLedger(
        version=1,
        kind="orders_v2_policy_consumption_ledger",
        entries=(rewritten, appended),
    )
    patch = OrdersV2PolicyConsumptionPatchArtifact(
        version=1,
        kind="orders_v2_policy_consumption_patch_candidate",
        review_fingerprint="c" * 64,
        current_ledger_fingerprint=previous.ledger_fingerprint,
        proposed_entry_fingerprint=appended.entry_fingerprint,
        expected_next_sequence=2,
        resulting_ledger_fingerprint=candidate.ledger_fingerprint,
        append_validation_passed=True,
        manual_version_control_commit_required=True,
        ledger_mutation_permitted=False,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=CONSUMPTION_PATCH_BLOCKER,
    )

    with pytest.raises(ValueError, match="rewrites historical entries"):
        attest_orders_v2_policy_consumption_commit_candidate(
            previous_ledger=previous,
            candidate_ledger=candidate,
            patch=patch,
        )


def test_commit_attestation_model_rejects_mutation_tamper() -> None:
    previous, candidate, patch = _fixture()
    attestation = attest_orders_v2_policy_consumption_commit_candidate(
        previous_ledger=previous,
        candidate_ledger=candidate,
        patch=patch,
    )
    payload = attestation.model_dump(mode="python")
    payload["ledger_mutation_permitted"] = True

    with pytest.raises(ValidationError):
        OrdersV2PolicyConsumptionCommitAttestation.model_validate(payload)
