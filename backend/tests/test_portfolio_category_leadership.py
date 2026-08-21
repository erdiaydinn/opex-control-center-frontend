from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_portfolio_category_leadership.py"
SPEC = importlib.util.spec_from_file_location("eay_validate_portfolio_category_leadership", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_contracts(tmp_path: Path, mutate) -> None:
    (tmp_path / "config").mkdir()
    portfolio = json.loads((ROOT / "config/eay_portfolio_category_leadership.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "config/eay_category_leadership_gates.json").read_text(encoding="utf-8"))
    mutate(portfolio, legacy)
    (tmp_path / "config/eay_portfolio_category_leadership.json").write_text(
        json.dumps(portfolio, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "config/eay_category_leadership_gates.json").write_text(
        json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
    )


def test_current_portfolio_contract_is_valid_and_complete() -> None:
    manifest = MODULE.validate_portfolio(ROOT)
    summary = manifest["_validation_summary"]
    assert summary["modules"] == 16
    assert summary["gates"] == 48
    assert summary["commercial_modules"] >= 10
    assert summary["unresolved_external_evidence_gates"] > 0


def test_missing_priority_fails_closed(tmp_path: Path) -> None:
    def mutate(portfolio, _legacy):
        portfolio["modules"][0]["gates"] = portfolio["modules"][0]["gates"][:2]

    _write_contracts(tmp_path, mutate)
    with pytest.raises(MODULE.PortfolioGateError, match="exactly one P0, P1 and P2"):
        MODULE.validate_portfolio(tmp_path)


def test_commercial_module_cannot_require_another_commercial_module(tmp_path: Path) -> None:
    def mutate(portfolio, _legacy):
        module = next(item for item in portfolio["modules"] if item["module_id"] == "inventory")
        module["required_commercial_dependencies"] = ["planogram"]

    _write_contracts(tmp_path, mutate)
    with pytest.raises(MODULE.PortfolioGateError, match="may not require another commercial module"):
        MODULE.validate_portfolio(tmp_path)


def test_missing_external_evidence_requires_an_explicit_blocker(tmp_path: Path) -> None:
    def mutate(portfolio, _legacy):
        module = next(item for item in portfolio["modules"] if item["module_id"] == "jarvis")
        module["gates"][0]["blocker"] = ""

    _write_contracts(tmp_path, mutate)
    with pytest.raises(MODULE.PortfolioGateError, match="blocker must be a non-empty string"):
        MODULE.validate_portfolio(tmp_path)


def test_leadership_claim_cannot_open_while_external_gates_are_unresolved(tmp_path: Path) -> None:
    def mutate(portfolio, _legacy):
        module = next(item for item in portfolio["modules"] if item["module_id"] == "workforce")
        module["claims"]["category_leadership_permitted"] = True

    _write_contracts(tmp_path, mutate)
    with pytest.raises(MODULE.PortfolioGateError, match="category leadership cannot be claimed"):
        MODULE.validate_portfolio(tmp_path)


def test_synthetic_reference_cannot_be_promoted_as_verified_external(tmp_path: Path) -> None:
    def mutate(portfolio, _legacy):
        module = next(item for item in portfolio["modules"] if item["module_id"] == "planogram")
        gate = module["gates"][0]
        gate["production_evidence_state"] = "verified_external"
        gate["external_evidence_refs"] = ["artifact:synthetic-store-fixture-proof"]

    _write_contracts(tmp_path, mutate)
    with pytest.raises(MODULE.PortfolioGateError, match="synthetic/test evidence cannot be marked verified_external"):
        MODULE.validate_portfolio(tmp_path)


def test_existing_module_inventory_cannot_be_silently_dropped(tmp_path: Path) -> None:
    def mutate(portfolio, _legacy):
        portfolio["modules"] = [
            item for item in portfolio["modules"] if item["module_id"] != "academy"
        ]

    _write_contracts(tmp_path, mutate)
    with pytest.raises(MODULE.PortfolioGateError, match="must exactly preserve"):
        MODULE.validate_portfolio(tmp_path)
