"""Runtime integrity validation for Live Company Reality decision receipts.

Pydantic ``model_copy`` and other in-process object operations can bypass normal
validation. Decision and execution boundaries therefore re-validate the full
serialized receipt before trusting its status or firm-claim flag. A stale or
mutated fingerprint fails closed.
"""

from __future__ import annotations

from .live_company_readiness import DecisionTruthReceipt

DECISION_TRUTH_INTEGRITY_CONTRACT = "eay-decision-truth-integrity-v1"


def validate_decision_truth_receipt_integrity(
    receipt: DecisionTruthReceipt,
) -> DecisionTruthReceipt:
    """Return a fully revalidated receipt or raise on semantic/integrity drift."""

    return DecisionTruthReceipt.model_validate(receipt.model_dump(mode="json"))
