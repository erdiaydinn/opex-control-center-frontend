#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

MATRIX = Path("config/eay_security_item4_adversarial_matrix.json")
REQUIRED = {
    "cross_tenant_api_rls",
    "bearer_ambiguity_session_fixation",
    "stale_identity_role_downgrade_privilege_escalation",
    "replay_internal_service",
    "idor_and_scope_smuggling",
    "csrf_cors_browser_trust",
    "proxy_tls_boundary",
    "sql_injection_dynamic_sql",
    "private_object_storage_receipt_replay",
    "export_scope_and_four_eyes",
    "tool_call_authorization_replay",
    "dependency_provenance_sbom",
    "signed_managed_build_gate",
}


def validate(root: Path) -> dict[str, object]:
    matrix = json.loads((root / MATRIX).read_text(encoding="utf-8"))
    assert matrix["schema_version"] == 1
    assert matrix["master_plan_item"] == "4/60"
    assert matrix["repository_acceptance_only"] is True
    assert matrix["production_ready"] is False
    assert matrix["frozen_security_baseline_pr"] == 16

    attacks = matrix["required_attack_classes"]
    assert set(attacks) == REQUIRED, sorted(set(attacks) ^ REQUIRED)
    for attack, contract in attacks.items():
        assert contract["state"] == "implemented_repository", (attack, contract["state"])
        evidence = contract.get("evidence")
        assert isinstance(evidence, list) and evidence, attack
        for relative in evidence:
            path = root / relative
            assert path.exists(), f"{attack}: missing evidence path {relative}"
            if path.is_file():
                assert path.stat().st_size > 0, f"{attack}: empty evidence path {relative}"

    external = matrix["external_acceptance_still_required"]
    assert isinstance(external, list) and len(external) >= 6
    return {
        "attack_classes": len(attacks),
        "external_acceptance_gates": len(external),
        "production_ready": False,
    }


def main() -> int:
    summary = validate(Path.cwd())
    print(
        "EAY Security item 4 matrix: PASS "
        f"attack_classes={summary['attack_classes']} "
        f"external_gates={summary['external_acceptance_gates']} production_ready=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
