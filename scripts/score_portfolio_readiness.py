#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MANIFEST = Path("config/eay_portfolio_category_leadership.json")
PRIORITY_WEIGHTS = {"P0": 0.50, "P1": 0.30, "P2": 0.20}
IMPLEMENTATION_FACTORS = {
    "implemented_repository": 1.0,
    "partial_repository": 0.5,
    "planned": 0.0,
}
EVIDENCE_FACTORS = {
    "verified_external": 1.0,
    "not_required": 1.0,
    "missing_external": 0.0,
}


def _score(module: dict[str, Any]) -> dict[str, object]:
    repository_score = 0.0
    production_score = 0.0
    p0_external_blocked = False
    for gate in module["gates"]:
        weight = PRIORITY_WEIGHTS[gate["priority"]]
        implementation = IMPLEMENTATION_FACTORS[gate["implementation_state"]]
        evidence = EVIDENCE_FACTORS[gate["production_evidence_state"]]
        repository_score += weight * implementation
        production_score += weight * implementation * evidence
        if gate["priority"] == "P0" and evidence == 0.0:
            p0_external_blocked = True

    repository_percent = round(repository_score * 100, 1)
    production_percent = round(production_score * 100, 1)
    return {
        "module_id": module["module_id"],
        "repository_readiness_percent": repository_percent,
        "production_readiness_percent": production_percent,
        "production_ready_claim_permitted": bool(
            module["claims"]["production_ready"] and not p0_external_blocked
        ),
        "p0_external_blocked": p0_external_blocked,
    }


def score_portfolio(root: Path) -> dict[str, object]:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    modules = [_score(module) for module in manifest["modules"]]
    return {
        "schema_version": 1,
        "method": {
            "priority_weights": PRIORITY_WEIGHTS,
            "implementation_factors": IMPLEMENTATION_FACTORS,
            "external_evidence_factors": EVIDENCE_FACTORS,
            "rule": "production readiness never exceeds repository readiness and missing external evidence contributes zero production points",
        },
        "modules": modules,
        "portfolio": {
            "repository_readiness_percent": round(
                sum(item["repository_readiness_percent"] for item in modules) / len(modules), 1
            ),
            "production_readiness_percent": round(
                sum(item["production_readiness_percent"] for item in modules) / len(modules), 1
            ),
            "production_ready_claim_permitted": all(
                bool(item["production_ready_claim_permitted"]) for item in modules
            ),
        },
    }


def main() -> int:
    result = score_portfolio(Path.cwd())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
