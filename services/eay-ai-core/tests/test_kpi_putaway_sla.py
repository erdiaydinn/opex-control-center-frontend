from datetime import date

import pytest

from app.kpi_putaway_sla import (
    PutawaySlaContract,
    evaluate_putaway_sla,
    resolve_putaway_sla_contract,
)


def contract(**kwargs):
    data = dict(
        contract_id="ops.putaway.sla.v1",
        version="2026.1",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        st_cdc_minutes=240,
        st_other_minutes=960,
        po_minutes=240,
        city_offsets_minutes={"Diyarbakır": 120, "Antalya": 60},
        schema_evidence_fingerprint="a" * 64,
        reviewed=True,
        reviewer="ops-reviewer",
    )
    data.update(kwargs)
    return PutawaySlaContract(**data)


def test_resolves_single_effective_version():
    old = contract(
        version="2026.1",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    current = contract(
        version="2026.2",
        effective_from=date(2026, 7, 1),
        effective_to=None,
    )
    resolved = resolve_putaway_sla_contract([old, current], as_of=date(2026, 8, 11))
    assert resolved.version == "2026.2"


def test_overlapping_versions_fail_closed():
    first = contract(effective_from=date(2026, 1, 1), effective_to=None)
    second = contract(version="2026.2", effective_from=date(2026, 7, 1), effective_to=None)
    with pytest.raises(ValueError, match="putaway_sla_ambiguous_effective_contract"):
        resolve_putaway_sla_contract([first, second], as_of=date(2026, 8, 11))


def test_human_review_is_required():
    with pytest.raises(ValueError, match="putaway_sla_human_review_required"):
        resolve_putaway_sla_contract(
            [contract(reviewed=False, reviewer=None)],
            as_of=date(2026, 8, 11),
        )


def test_st_cdc_and_po_use_240_minute_thresholds():
    contracts = [contract()]
    cdc = evaluate_putaway_sla(
        contracts,
        as_of=date(2026, 8, 11),
        inbound_kind="ST_CDC",
        elapsed_minutes=240,
    )
    po = evaluate_putaway_sla(
        contracts,
        as_of=date(2026, 8, 11),
        inbound_kind="PO",
        elapsed_minutes=241,
    )
    assert cdc.threshold_minutes == 240 and cdc.compliant is True
    assert po.threshold_minutes == 240 and po.compliant is False


def test_st_other_applies_only_explicit_reviewed_city_offset():
    contracts = [contract()]
    diyarbakir = evaluate_putaway_sla(
        contracts,
        as_of=date(2026, 8, 11),
        inbound_kind="ST_OTHER",
        city="diyarbakır",
        elapsed_minutes=1080,
    )
    unknown_city = evaluate_putaway_sla(
        contracts,
        as_of=date(2026, 8, 11),
        inbound_kind="ST_OTHER",
        city="İzmir",
        elapsed_minutes=961,
    )
    assert diyarbakir.threshold_minutes == 1080 and diyarbakir.compliant is True
    assert unknown_city.threshold_minutes == 960 and unknown_city.compliant is False


def test_contract_fingerprint_changes_with_effective_rule():
    baseline = contract()
    changed = contract(city_offsets_minutes={"Diyarbakır": 180, "Antalya": 60})
    assert len(baseline.fingerprint) == 64
    assert baseline.fingerprint != changed.fingerprint


def test_invalid_schema_evidence_fingerprint_fails_closed():
    with pytest.raises(ValueError, match="putaway_sla_invalid_fingerprint:schema_evidence"):
        resolve_putaway_sla_contract(
            [contract(schema_evidence_fingerprint="bad")],
            as_of=date(2026, 8, 11),
        )
