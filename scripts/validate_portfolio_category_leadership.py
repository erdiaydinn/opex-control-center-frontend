#!/usr/bin/env python3
"""Validate the EAY portfolio category-leadership contract fail closed.

This validator keeps four boundaries separate:

1. repository implementation state,
2. real external/field/production evidence,
3. standalone commercial-module value,
4. category-parity / leadership / production claims.

A benchmark product name is a comparison target only. It is not accepted as proof
that the product currently implements a particular capability, and repository CI is
never accepted as external production evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path("config/eay_portfolio_category_leadership.json")
ALLOWED_MODULE_KINDS = {"commercial_module", "shared_capability"}


class PortfolioGateError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PortfolioGateError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortfolioGateError(f"cannot load JSON contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PortfolioGateError(f"JSON contract must be an object: {path}")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    _require(isinstance(value, str) and value.strip(), f"{label} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    _require(isinstance(value, list), f"{label} must be a list")
    _require(all(isinstance(item, str) and item.strip() for item in value), f"{label} must contain only non-empty strings")
    normalized = [item.strip() for item in value]
    _require(len(normalized) == len(set(normalized)), f"{label} must not contain duplicates")
    if not allow_empty:
        _require(bool(normalized), f"{label} must not be empty")
    return normalized


def _gate_resolves_external_evidence(gate: dict[str, Any]) -> bool:
    return gate["production_evidence_state"] in {"not_required", "verified_external"}


def _validate_claims(module_id: str, module: dict[str, Any], gates: list[dict[str, Any]]) -> None:
    claims = module.get("claims")
    _require(isinstance(claims, dict), f"{module_id}: claims are required")
    for key in ("category_parity_permitted", "category_leadership_permitted", "production_ready"):
        _require(isinstance(claims.get(key), bool), f"{module_id}: claim {key} must be boolean")

    p0 = [gate for gate in gates if gate["priority"] == "P0"]
    p0_p1 = [gate for gate in gates if gate["priority"] in {"P0", "P1"}]

    parity_eligible = all(
        gate["implementation_state"] == "implemented_repository" and _gate_resolves_external_evidence(gate)
        for gate in p0_p1
    )
    leadership_eligible = all(
        gate["implementation_state"] == "implemented_repository" and _gate_resolves_external_evidence(gate)
        for gate in gates
    )
    production_eligible = all(
        gate["implementation_state"] == "implemented_repository" and _gate_resolves_external_evidence(gate)
        for gate in p0
    )

    if claims["category_parity_permitted"]:
        _require(parity_eligible, f"{module_id}: category parity cannot be claimed while P0/P1 gates are unresolved")
    if claims["category_leadership_permitted"]:
        _require(leadership_eligible, f"{module_id}: category leadership cannot be claimed while any gate is unresolved")
    if claims["production_ready"]:
        _require(production_eligible, f"{module_id}: production readiness cannot be claimed while P0 evidence is unresolved")


def validate_portfolio(repo_root: Path) -> dict[str, Any]:
    manifest = _load_json(repo_root / MANIFEST_PATH)
    _require(manifest.get("schema_version") == 1, "unsupported portfolio category-leadership schema")
    _require(manifest.get("portfolio_stage") == "rise_era_category_leadership", "unexpected portfolio stage")

    policy = manifest.get("portfolio_policy")
    _require(isinstance(policy, dict), "portfolio_policy is required")
    required_priorities = _string_list(policy.get("required_priorities"), "required_priorities", allow_empty=False)
    _require(required_priorities == ["P0", "P1", "P2"], "required priorities must remain exactly P0/P1/P2")
    implementation_states = set(_string_list(policy.get("implementation_states"), "implementation_states", allow_empty=False))
    evidence_states = set(_string_list(policy.get("production_evidence_states"), "production_evidence_states", allow_empty=False))
    _require(
        implementation_states == {"implemented_repository", "partial_repository", "planned"},
        "unexpected implementation-state contract",
    )
    _require(
        evidence_states == {"not_required", "missing_external", "verified_external"},
        "unexpected production-evidence-state contract",
    )
    _require(policy.get("commercial_core_may_require_other_commercial_module") is False, "commercial module lock-in must remain forbidden")
    _require(policy.get("cross_module_integrations_must_be_optional") is True, "cross-module integrations must remain optional")
    _require(policy.get("leadership_claim_requires_all_p0_p1_implemented") is True, "leadership implementation gate must remain enabled")
    _require(policy.get("leadership_claim_requires_all_external_evidence_verified") is True, "leadership evidence gate must remain enabled")
    _require(policy.get("production_ready_claim_requires_all_p0_external_evidence_verified") is True, "production evidence gate must remain enabled")

    truth = manifest.get("truth_boundary")
    _require(isinstance(truth, dict), "truth_boundary is required")
    for key in (
        "portfolio_category_parity_permitted",
        "portfolio_category_leadership_permitted",
        "portfolio_production_ready",
        "repository_green_is_production_ready",
        "synthetic_evidence_is_external_evidence",
        "market_benchmark_target_is_verified_feature_claim",
    ):
        _require(truth.get(key) is False, f"truth boundary {key} must remain false until separately evidenced")

    source_gap_catalog = _nonempty_string(manifest.get("source_gap_catalog"), "source_gap_catalog")
    legacy = _load_json(repo_root / source_gap_catalog)
    legacy_modules = legacy.get("modules")
    _require(isinstance(legacy_modules, dict) and legacy_modules, "legacy category-leadership gap catalog is invalid")

    modules = manifest.get("modules")
    _require(isinstance(modules, list) and modules, "modules must be a non-empty list")
    module_ids: list[str] = []
    for raw in modules:
        _require(isinstance(raw, dict), "each module contract must be an object")
        module_ids.append(_nonempty_string(raw.get("module_id"), "module_id"))
    _require(len(module_ids) == len(set(module_ids)), "duplicate module_id entries are forbidden")
    module_id_set = set(module_ids)
    _require(
        module_id_set == set(legacy_modules),
        "portfolio module inventory must exactly preserve the existing category-leadership gap catalog",
    )

    total_gates = 0
    unresolved_external = 0
    commercial_modules = 0

    for module in modules:
        module_id = module["module_id"]
        module_kind = module.get("module_kind")
        _require(module_kind in ALLOWED_MODULE_KINDS, f"{module_id}: invalid module_kind")
        standalone = module.get("standalone_sale_required")
        _require(isinstance(standalone, bool), f"{module_id}: standalone_sale_required must be boolean")

        required_dependencies = _string_list(
            module.get("required_commercial_dependencies"),
            f"{module_id}.required_commercial_dependencies",
        )
        optional_integrations = _string_list(module.get("optional_integrations"), f"{module_id}.optional_integrations")
        _require(module_id not in optional_integrations, f"{module_id}: module cannot integrate with itself")
        _require(set(optional_integrations) <= module_id_set, f"{module_id}: unknown optional integration")

        if module_kind == "commercial_module":
            commercial_modules += 1
            _require(standalone is True, f"{module_id}: commercial modules must remain standalone-sale capable")
            _require(not required_dependencies, f"{module_id}: core workflow may not require another commercial module")
        else:
            _require(not required_dependencies, f"{module_id}: shared capability must not be coupled to commercial-module licensing")

        _string_list(module.get("benchmark_products"), f"{module_id}.benchmark_products", allow_empty=False)
        benchmark_note = _nonempty_string(module.get("benchmark_note"), f"{module_id}.benchmark_note").lower()
        _require("not a claim" in benchmark_note, f"{module_id}: benchmark note must preserve the no-feature-claim boundary")
        _string_list(module.get("repository_evidence_refs"), f"{module_id}.repository_evidence_refs", allow_empty=False)

        raw_gates = module.get("gates")
        _require(isinstance(raw_gates, list), f"{module_id}: gates must be a list")
        _require(len(raw_gates) == len(required_priorities), f"{module_id}: must define exactly one P0, P1 and P2 gate")

        priorities: list[str] = []
        gap_ids: list[str] = []
        gates: list[dict[str, Any]] = []
        for raw_gate in raw_gates:
            _require(isinstance(raw_gate, dict), f"{module_id}: gate must be an object")
            priority = _nonempty_string(raw_gate.get("priority"), f"{module_id}.gate.priority")
            _require(priority in required_priorities, f"{module_id}: unknown priority {priority}")
            priorities.append(priority)
            gap_ids.append(_nonempty_string(raw_gate.get("gap_id"), f"{module_id}.{priority}.gap_id"))
            _nonempty_string(raw_gate.get("capability"), f"{module_id}.{priority}.capability")
            _nonempty_string(raw_gate.get("acceptance"), f"{module_id}.{priority}.acceptance")
            _nonempty_string(raw_gate.get("evidence_type"), f"{module_id}.{priority}.evidence_type")

            implementation_state = raw_gate.get("implementation_state")
            production_evidence_state = raw_gate.get("production_evidence_state")
            _require(implementation_state in implementation_states, f"{module_id}.{priority}: invalid implementation_state")
            _require(production_evidence_state in evidence_states, f"{module_id}.{priority}: invalid production_evidence_state")

            blocker = raw_gate.get("blocker")
            external_refs = _string_list(raw_gate.get("external_evidence_refs"), f"{module_id}.{priority}.external_evidence_refs")
            if production_evidence_state == "missing_external":
                _nonempty_string(blocker, f"{module_id}.{priority}.blocker")
                _require(not external_refs, f"{module_id}.{priority}: missing external evidence may not carry promotion-grade refs")
                unresolved_external += 1
            elif production_evidence_state == "verified_external":
                _require(external_refs, f"{module_id}.{priority}: verified external evidence requires exact refs")
                for ref in external_refs:
                    lowered = ref.lower()
                    _require(
                        all(token not in lowered for token in ("synthetic", "fixture", "mock", "fake")),
                        f"{module_id}.{priority}: synthetic/test evidence cannot be marked verified_external",
                    )
            else:
                _require(not external_refs, f"{module_id}.{priority}: not_required evidence must not carry external refs")

            gates.append(raw_gate)
            total_gates += 1

        _require(priorities == required_priorities, f"{module_id}: gates must be ordered P0, P1, P2")
        _require(len(gap_ids) == len(set(gap_ids)), f"{module_id}: duplicate gap_id entries are forbidden")
        _validate_claims(module_id, module, gates)

    _require(total_gates == len(modules) * 3, "portfolio must have exactly three gates per module")
    _require(commercial_modules > 0, "portfolio must contain commercial modules")

    manifest["_validation_summary"] = {
        "modules": len(modules),
        "commercial_modules": commercial_modules,
        "gates": total_gates,
        "unresolved_external_evidence_gates": unresolved_external,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    manifest = validate_portfolio(args.repo_root.resolve())
    summary = manifest["_validation_summary"]
    print(
        "EAY portfolio category leadership: PASS "
        f"modules={summary['modules']} commercial={summary['commercial_modules']} "
        f"gates={summary['gates']} unresolved_external={summary['unresolved_external_evidence_gates']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PortfolioGateError as exc:
        print(f"EAY portfolio category leadership: FAIL: {exc}")
        raise SystemExit(1) from exc
