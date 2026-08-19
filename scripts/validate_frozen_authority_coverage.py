#!/usr/bin/env python3
"""Fail-closed validation for the frozen #15/#16 authority coverage matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "config/eay_frozen_authority_coverage_matrix_v1.json"
EXTENSION_PATH = ROOT / "config/eay_frozen_authority_coverage_extension_v2.json"

EXPECTED_SOURCES = {
    15: {
        "head_sha": "9e1422df2a584b71593c2f6188d26c8ab4ab4c15",
        "frozen": True,
        "direct_ancestor_of_canonical": False,
    },
    16: {
        "head_sha": "6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d",
        "frozen": True,
        "direct_ancestor_of_canonical": True,
    },
}

REQUIRED_CAPABILITIES = {
    "ai_core.legal.temporal_grounded_rag",
    "ai_core.regulatory.authority_lineage_conflict",
    "ai_core.bigquery.governed_named_query_execution",
    "ai_core.kpi.schema_semantics_activation",
    "ai_core.learning.training_human_gate",
    "ai_core.model_registry.license_promotion_canary",
    "ai_core.vision.provenance_human_review",
    "ai_core.repository_intelligence.provenance",
    "ai_core.voice.governed_tool_execution",
    "ai_core.privacy.safety_observability",
    "ai_core.employment.temporal_policy",
    "ai_core.payroll.period_policy",
    "ai_core.company.dataset_domain_governance",
    "ai_core.tool_intent_contract_router",
    "ai_core.legal.review_verification_promotion",
    "ai_core.release.evidence_canary_registry",
    "ai_core.multilingual.language_learning",
    "ai_core.training.integrity_manifest_export",
    "ai_core.model_artifact.provenance_lifecycle",
    "ai_core.vision.retention_review_lineage",
    "ai_core.voice.deployment_release_attestation",
    "ai_core.voice.session_streaming_protocol",
    "ai_core.schema.source_contracts",
    "security.tenant_rbac_rls_boundary",
    "security.oidc_external_identity_preauth",
    "security.internal_service_identity_replay",
    "security.browser_frontend_authorization_boundary",
    "security.network_tls_cors_proxy_boundary",
    "security.sql_database_role_boundary",
    "security.dockos_quarantine_platform_boundary",
    "security.jarvis.grant_admission_audit_envelope",
}

FORBIDDEN_CANONICAL_FRAGMENTS = {
    "feature/eay-ai-core-v0.1",
    "feature/phase-1-security-hardening",
    "0011_jarvis_audit_hash_chain",
}

ALLOWED_DISPOSITIONS = {
    "ported_to_current_canonical",
    "ported_and_strengthened",
    "ancestry_preserved_and_revalidated",
    "ancestry_preserved_and_strengthened",
}


def fail(message: str) -> None:
    raise SystemExit(f"frozen-authority coverage validation failed: {message}")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot load {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def load_matrix() -> dict:
    matrix = load_json(MATRIX_PATH)
    extension = load_json(EXTENSION_PATH)
    expected_base = MATRIX_PATH.relative_to(ROOT).as_posix()
    if extension.get("schema_version") != 1:
        fail("coverage extension schema_version must be 1")
    if extension.get("extends") != expected_base:
        fail(f"coverage extension must extend {expected_base}")
    if extension.get("historical_source_prs") != [15]:
        fail("coverage extension must remain bound to frozen PR #15")
    boundary = extension.get("proof_boundary")
    if not isinstance(boundary, str) or len(boundary.strip()) < 48:
        fail("coverage extension proof_boundary must be explicit")
    extension_capabilities = extension.get("capabilities")
    if not isinstance(extension_capabilities, list) or not extension_capabilities:
        fail("coverage extension capabilities must be a non-empty list")
    base_capabilities = matrix.get("capabilities")
    if not isinstance(base_capabilities, list) or not base_capabilities:
        fail("base capabilities must be a non-empty list")
    matrix = dict(matrix)
    matrix["capabilities"] = [*base_capabilities, *extension_capabilities]
    return matrix


def require_file(relative_path: str, *, capability_id: str, kind: str) -> None:
    if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        fail(f"{capability_id}: invalid {kind} path {relative_path!r}")
    for fragment in FORBIDDEN_CANONICAL_FRAGMENTS:
        if fragment in relative_path:
            fail(f"{capability_id}: forbidden historical canonical reference {relative_path}")
    target = ROOT / relative_path
    if not target.is_file():
        fail(f"{capability_id}: missing {kind} file {relative_path}")


def validate() -> dict:
    matrix = load_matrix()
    if matrix.get("schema_version") != 1:
        fail("schema_version must be 1")
    if matrix.get("canonical_pr") != 163:
        fail("canonical_pr must remain #163 for this matrix version")
    if matrix.get("canonical_branch") != "agent/jarvis-platform-security-consolidation-v1":
        fail("unexpected canonical_branch")

    sources = matrix.get("historical_sources")
    if not isinstance(sources, list) or len(sources) != 2:
        fail("historical_sources must contain exactly frozen PR #15 and #16")
    by_pr = {item.get("pr"): item for item in sources if isinstance(item, dict)}
    if set(by_pr) != set(EXPECTED_SOURCES):
        fail("historical_sources must be exactly PR #15 and #16")
    for pr, expected in EXPECTED_SOURCES.items():
        observed = by_pr[pr]
        for key, value in expected.items():
            if observed.get(key) != value:
                fail(f"PR #{pr} {key} mismatch: expected {value!r}, got {observed.get(key)!r}")

    proof_boundary = matrix.get("proof_boundary")
    if not isinstance(proof_boundary, list) or len(proof_boundary) < 4:
        fail("proof_boundary must explicitly preserve repository-vs-production truth")

    capabilities = matrix.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        fail("capabilities must be a non-empty list")

    ids: set[str] = set()
    represented_sources: set[int] = set()
    for capability in capabilities:
        if not isinstance(capability, dict):
            fail("every capability must be an object")
        capability_id = capability.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            fail("every capability requires a non-empty id")
        if capability_id in ids:
            fail(f"duplicate capability id {capability_id}")
        ids.add(capability_id)

        source_prs = capability.get("source_prs")
        if not isinstance(source_prs, list) or not source_prs:
            fail(f"{capability_id}: source_prs must be non-empty")
        if not set(source_prs).issubset(EXPECTED_SOURCES):
            fail(f"{capability_id}: source_prs may contain only frozen PR #15/#16")
        represented_sources.update(source_prs)

        disposition = capability.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            fail(f"{capability_id}: invalid disposition {disposition!r}")

        canonical_paths = capability.get("canonical_paths")
        evidence_tests = capability.get("evidence_tests")
        if not isinstance(canonical_paths, list) or not canonical_paths:
            fail(f"{capability_id}: canonical_paths must be non-empty")
        if not isinstance(evidence_tests, list) or not evidence_tests:
            fail(f"{capability_id}: evidence_tests must be non-empty")

        for relative_path in canonical_paths:
            if not isinstance(relative_path, str):
                fail(f"{capability_id}: canonical path must be a string")
            require_file(relative_path, capability_id=capability_id, kind="canonical")
        for relative_path in evidence_tests:
            if not isinstance(relative_path, str):
                fail(f"{capability_id}: evidence test path must be a string")
            if "/tests/test_" not in relative_path or not relative_path.endswith(".py"):
                fail(f"{capability_id}: evidence path is not an explicit pytest file: {relative_path}")
            require_file(relative_path, capability_id=capability_id, kind="evidence")

        if not capability.get("evidence_lane"):
            fail(f"{capability_id}: evidence_lane is required")
        truth_boundary = capability.get("truth_boundary")
        if not isinstance(truth_boundary, str) or len(truth_boundary.strip()) < 24:
            fail(f"{capability_id}: truth_boundary must be explicit")

    missing = REQUIRED_CAPABILITIES - ids
    if missing:
        fail(f"missing required capabilities: {', '.join(sorted(missing))}")
    unexpected = ids - REQUIRED_CAPABILITIES
    if unexpected:
        fail(f"unreviewed capabilities present: {', '.join(sorted(unexpected))}")
    if represented_sources != set(EXPECTED_SOURCES):
        fail("both frozen PR #15 and #16 must be represented")

    return matrix


def main() -> int:
    matrix = validate()
    if "--print-core-tests" in sys.argv:
        tests = sorted(
            {
                path.removeprefix("services/core-api/")
                for capability in matrix["capabilities"]
                if capability["evidence_lane"] == "frozen-authority-coverage"
                for path in capability["evidence_tests"]
                if path.startswith("services/core-api/tests/")
            }
        )
        print(" ".join(tests))
        return 0
    if "--print-ai-tests" in sys.argv:
        tests = sorted(
            {
                path.removeprefix("services/eay-ai-core/")
                for capability in matrix["capabilities"]
                if capability["evidence_lane"] == "ai-core-execution"
                for path in capability["evidence_tests"]
                if path.startswith("services/eay-ai-core/tests/")
            }
        )
        print(" ".join(tests))
        return 0
    print(
        "frozen-authority coverage OK: "
        f"{len(matrix['capabilities'])} capabilities, frozen PRs #15/#16, all current paths present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
