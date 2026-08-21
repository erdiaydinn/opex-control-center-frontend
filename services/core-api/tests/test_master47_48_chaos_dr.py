from pathlib import Path

from app.sre.chaos_dr import (
    ChaosResult,
    DrResult,
    chaos_result_accepted,
    dr_result_accepted,
    load_chaos_dr_contract,
)

ROOT = Path(__file__).resolve().parents[3]


def test_all_master47_scenarios_present_and_synthetic_cannot_pass() -> None:
    contract = load_chaos_dr_contract(
        ROOT / "docs/governance/eay_chaos_dr_acceptance.json"
    )
    assert {
        "db_restart",
        "redis_unavailable",
        "bigquery_denial",
        "retry_storm",
    } <= set(contract["chaos_scenarios"])

    synthetic = ChaosResult(
        scenario="db_restart",
        environment="ci",
        measured=True,
        passed_invariants=tuple(contract["required_invariants"]),
        provenance="ci:1",
    )
    assert not chaos_result_accepted(contract, synthetic)

    measured = ChaosResult(
        scenario="db_restart",
        environment="managed-staging",
        measured=True,
        passed_invariants=tuple(contract["required_invariants"]),
        provenance="chaos:approved:1",
    )
    assert chaos_result_accepted(contract, measured)


def test_chaos_requires_every_governed_invariant() -> None:
    contract = load_chaos_dr_contract(
        ROOT / "docs/governance/eay_chaos_dr_acceptance.json"
    )
    incomplete = tuple(contract["required_invariants"][:-1])
    result = ChaosResult(
        scenario="retry_storm",
        environment="managed-staging",
        measured=True,
        passed_invariants=incomplete,
        provenance="chaos:2",
    )
    assert not chaos_result_accepted(contract, result)


def test_dr_requires_measured_rpo_rto_in_managed_environment() -> None:
    assert not dr_result_accepted(
        DrResult("ci", True, 0, 20, "run:1")
    )
    assert not dr_result_accepted(
        DrResult("managed-staging", True, None, 20, "run:2")
    )
    assert dr_result_accepted(
        DrResult("managed-staging", True, 30, 180, "restore:approved")
    )
