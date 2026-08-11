import pytest

from app.kpi_putaway_inbound_classification import (
    PutawayInboundClassificationContract,
    classify_putaway_inbound,
    verify_putaway_inbound_classification_contract,
)


def contract(**overrides):
    payload = {
        "contract_id": "putaway.inbound.v1",
        "raw_to_kind": {
            "st_cdc": "ST_CDC",
            "stock transfer cdc": "ST_CDC",
            "st_other": "ST_OTHER",
            "po": "PO",
            "purchase order": "PO",
        },
        "reviewed_at": "2026-08-11T12:00:00Z",
        "reviewer": "ops-metric-owner",
        "reviewed": True,
    }
    payload.update(overrides)
    return PutawayInboundClassificationContract(**payload)


def test_verified_classification_normalizes_reviewed_aliases_only():
    verified = verify_putaway_inbound_classification_contract(contract())
    assert classify_putaway_inbound(" Stock Transfer CDC ", verified_contract=verified) == "ST_CDC"
    assert classify_putaway_inbound("purchase order", verified_contract=verified) == "PO"
    assert len(verified["classification_fingerprint"]) == 64


def test_unknown_inbound_value_fails_closed():
    verified = verify_putaway_inbound_classification_contract(contract())
    with pytest.raises(ValueError, match="putaway_inbound_classification_unknown_raw_value"):
        classify_putaway_inbound("mystery-transfer", verified_contract=verified)


def test_contract_rejects_unreviewed_mapping():
    with pytest.raises(ValueError, match="putaway_inbound_classification_human_review_required"):
        verify_putaway_inbound_classification_contract(contract(reviewed=False, reviewer=None))


def test_contract_rejects_invalid_target_kind():
    with pytest.raises(ValueError, match="putaway_inbound_classification_invalid_kind"):
        verify_putaway_inbound_classification_contract(
            contract(raw_to_kind={"weird": "AUTO_GUESS"})
        )


def test_blank_raw_value_rejected():
    with pytest.raises(ValueError, match="putaway_inbound_classification_blank_raw_value"):
        verify_putaway_inbound_classification_contract(
            contract(raw_to_kind={" ": "PO"})
        )
