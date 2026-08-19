#!/usr/bin/env python3
"""Fail-closed validation for the frozen #15/#16 authority coverage matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "config/eay_frozen_authority_coverage_matrix_v1.json"
EXTENSION_V2_PATH = ROOT / "config/eay_frozen_authority_coverage_extension_v2.json"
EXTENSION_V3_PATH = ROOT / "config/eay_frozen_authority_coverage_extension_v3.json"

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
    "ai_core.regulatory.atomic_watch_classifier",
    "ai_core.rag.evidence_eval_guardrails",
    "ai_core.kpi.aggregation_dimension_unit_policy",
    "ai_core.kpi.nsfr_activation",
    "ai_core.kpi.putaway_activation",
    "ai_core.kpi.runtime_query_release",
    "ai_core.kpi.registry_schema_integrity",
    "ai_core.voice.adapter_candidate_promotion",
    "ai_core.voice.local_audio_native_runtime",
    "ai_core.voice.execution_lineage_realtime_bridge",
    "ai_core.voice.tts_native_streaming",
    "ai_core.voice.ws_release_freshness",
    "ai_core.api.public_surface_guardrail",
    "security.tenant_rbac_rls_boundary",
    "security.oidc_external_identity_preauth",
    "security.internal_service_identity_replay",
    "security.browser_frontend_authorization_boundary",
    "security.network_tls_cors_proxy_boundary",
    "security.sql_database_role_boundary",
    "security.dockos_quarantine_platform_boundary",
    "security.jarvis.grant_admission_audit_envelope",
    "security.backup_role_secret_boundary",
    "security.system_role_bootstrap_integrity",
    "security.internal_assertion_adoption_contract",
    "security.core_audit_transactional_boundary",
    "security.identity_gateway_signing_secret_runtime",
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

ALLOWED_EVIDENCE_LANES = {
    "ai-core-execution",
    "frozen-authority-coverage",
    "identity-gateway-security",
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


def load_extension(
    path: Path,
    *,
    expected_parent: Path,
    expected_sources: list[int],
) -> list[dict]:
    extension = load_json(path)
    if extension.get("schema_version") != 1:
        fail(f"{path.relative_to(ROOT)} schema_version must be 1")
    expected_parent_value = expected_parent.relative_to(ROOT).as_posix()
    if extension.get("extends") != expected_parent_value:
        fail(f"{path.relative_to(ROOT)} must extend {expected_parent_value}")
    if extension.get("historical_source_prs") != expected_sources:
        fail(
            f"{path.relative_to(ROOT)} historical_source_prs must be "
            f"{expected_sources}"
        )
    boundary = extension.get("proof_boundary")
    if not isinstance(boundary, str) or len(boundary.strip()) < 48:
        fail(f"{path.relative_to(ROOT)} proof_boundary must be explicit")
    capabilities = extension.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        fail(f"{path.relative_to(ROOT)} capabilities must be a non-empty list")
    return capabilities


def load_matrix() -> dict:
    matrix = load_json(MATRIX_PATH)
    base_capabilities = matrix.get("capabilities")
    if not isinstance(base_capabilities, list) or not base_capabilities:
        fail("base capabilities must be a non-empty list")

    v2_capabilities = load_extension(
        EXTENSION_V2_PATH,
        expected_parent=MATRIX_PATH,
        expected_sources=[15],
    )
    v3_capabilities = load_extension(
        EXTENSION_V3_PATH,
        expected_parent=EXTENSION_V2_PATH,
        expected_sources=[15, 16],
    )

    matrix = dict(matrix)
    matrix["capabilities"] = [
        *base_capabilities,
        *v2_capabilities,
        *v3_capabilities,
    ]
    return matrix


def require_file(relative_path: str, *, capability_id: str, kind: str) -> None:
    path = Path(relative_path)
    if not relative_path or path.is_absolute() or ".." in path.parts:
        fail(f"{capability_id}: invalid {kind} path {relative_path!r}")
    for fragment in FORBIDDEN_CANONICAL_FRAGMENTS:
        if fragment in relative_path:
            fail(
                f"{capability_id}: forbidden historical canonical reference "
                f"{relative_path}"
            )
    if not (ROOT / relative_path).is_file():
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
                fail(
                    f"PR #{pr} {key} mismatch: expected {value!r}, "
                    f"got {observed.get(key)!r}"
                )

    proof_boundary = matrix.get("proof_boundary")
    if not isinstance(proof_boundary, list) or len(proof_boundary) < 4:
        fail("proof_boundary must explicitly preserve repository-vs-production truth")

    capabilities = matrix.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        fail("capabilities must be a non-empty list")

    ids: set[str] = set()
    represented_sources: set[int] = set()
    represented_lanes: set[str] = set()
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
                fail(
                    f"{capability_id}: evidence path is not an explicit pytest file: "
                    f"{relative_path}"
                )
            require_file(relative_path, capability_id=capability_id, kind="evidence")

        evidence_lane = capability.get("evidence_lane")
        if evidence_lane not in ALLOWED_EVIDENCE_LANES:
            fail(f"{capability_id}: invalid evidence_lane {evidence_lane!r}")
        represented_lanes.add(evidence_lane)

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
    if represented_lanes != ALLOWED_EVIDENCE_LANES:
        fail(
            "all exact-head evidence lanes must remain represented: "
            + ", ".join(sorted(ALLOWED_EVIDENCE_LANES))
        )

    return matrix


def selected_tests(matrix: dict, *, lane: str, prefix: str) -> list[str]:
    return sorted(
        {
            path.removeprefix(prefix)
            for capability in matrix["capabilities"]
            if capability["evidence_lane"] == lane
            for path in capability["evidence_tests"]
            if path.startswith(prefix)
        }
    )


def main() -> int:
    matrix = validate()
    if "--print-core-tests" in sys.argv:
        print(
            " ".join(
                selected_tests(
                    matrix,
                    lane="frozen-authority-coverage",
                    prefix="services/core-api/",
                )
            )
        )
        return 0
    if "--print-ai-tests" in sys.argv:
        print(
            " ".join(
                selected_tests(
                    matrix,
                    lane="ai-core-execution",
                    prefix="services/eay-ai-core/",
                )
            )
        )
        return 0
    if "--print-identity-tests" in sys.argv:
        print(
            " ".join(
                selected_tests(
                    matrix,
                    lane="identity-gateway-security",
                    prefix="services/identity-gateway/",
                )
            )
        )
        return 0

    print(
        "frozen-authority coverage OK: "
        f"{len(matrix['capabilities'])} capabilities, frozen PRs #15/#16, "
        "all current paths present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
