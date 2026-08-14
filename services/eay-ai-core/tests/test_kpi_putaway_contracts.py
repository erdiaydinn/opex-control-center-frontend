from datetime import date

import pytest

from app.kpi_putaway_contracts import PutawayQuantityContract, verify_putaway_activation
from app.kpi_putaway_sla import PutawaySlaContract


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


def reviewed_sla(**kwargs):
    data = dict(
        contract_id="ops.putaway.sla.v1",
        version="1.0",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        schema_evidence_fingerprint=FP_C,
        reviewed=True,
        reviewer="ops-reviewer",
    )
    data.update(kwargs)
    return PutawaySlaContract(**data)


def semantic():
    return {"metric": "putaway", "reviewed": True, "fingerprint": FP_A}


def schema(**kwargs):
    data = {
        "verified": True,
        "observed_fingerprint": FP_B,
        "evidence_fingerprint": FP_C,
    }
    data.update(kwargs)
    return data


def test_issue_quantity_uses_reviewed_formula():
    contract = PutawayQuantityContract()
    assert contract.issue_quantity(initial="12", on_shelf="7") == 5
    assert len(contract.fingerprint) == 64


def test_issue_quantity_rejects_on_shelf_above_initial():
    with pytest.raises(ValueError, match="on_shelf_exceeds_initial"):
        PutawayQuantityContract().issue_quantity(initial=3, on_shelf=4)


def test_issue_quantity_rejects_missing_and_negative_values():
    contract = PutawayQuantityContract()
    with pytest.raises(ValueError, match="putaway_quantity_missing"):
        contract.issue_quantity(initial=None, on_shelf=0)
    with pytest.raises(ValueError, match="putaway_quantity_invalid"):
        contract.issue_quantity(initial=1, on_shelf=-1)


def test_putaway_activation_binds_schema_sla_and_quantity_contract():
    bundle = verify_putaway_activation(
        semantic_verification=semantic(),
        schema_verification=schema(),
        sla_contracts=[reviewed_sla()],
        as_of=date(2026, 8, 10),
    )
    assert bundle.metric == "putaway"
    assert bundle.schema_evidence_fingerprint == FP_C
    assert len(bundle.sla_contract_fingerprint) == 64
    assert len(bundle.quantity_contract_fingerprint) == 64
    assert len(bundle.fingerprint) == 64


def test_putaway_activation_requires_human_reviewed_schema_evidence():
    with pytest.raises(ValueError, match="schema_evidence"):
        verify_putaway_activation(
            semantic_verification=semantic(),
            schema_verification=schema(evidence_fingerprint=None),
            sla_contracts=[reviewed_sla()],
            as_of=date(2026, 8, 10),
        )


def test_putaway_activation_rejects_sla_bound_to_different_schema_evidence():
    with pytest.raises(ValueError, match="sla_schema_evidence_mismatch"):
        verify_putaway_activation(
            semantic_verification=semantic(),
            schema_verification=schema(),
            sla_contracts=[reviewed_sla(schema_evidence_fingerprint="d" * 64)],
            as_of=date(2026, 8, 10),
        )


def test_putaway_activation_rejects_wrong_semantic_metric():
    bad = semantic()
    bad["metric"] = "prep"
    with pytest.raises(ValueError, match="semantic_verification_required"):
        verify_putaway_activation(
            semantic_verification=bad,
            schema_verification=schema(),
            sla_contracts=[reviewed_sla()],
            as_of=date(2026, 8, 10),
        )
