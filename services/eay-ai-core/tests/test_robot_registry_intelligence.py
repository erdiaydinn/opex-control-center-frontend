from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.playwright_computer_runtime import BrowserActionKind, LocatorKind
from app.robot_authoring_intelligence import RobotKind
from app.robot_registry_intelligence import (
    ApprovedRobotVersion,
    CompiledPlanKind,
    RobotCompilationScope,
    calculate_version_fingerprint,
    compile_approved_robot,
)

OUTCOME = "a" * 64
SOURCE = "b" * 64
CANDIDATE = "c" * 64
REGISTRY_CANDIDATE = "d" * 64


def scope(**overrides) -> RobotCompilationScope:
    values = {
        "tenant_id": "00000000-0000-4000-8000-0000000000a1",
        "company_id": "company-a",
        "objective_id": "daily-report",
        "allowed_hosts": frozenset({"api.acme.example", "portal.acme.example"}),
        "application_id": "acme-reporting",
        "tenant_scope_ref": "tenant-scope://tenant-a/company-a",
        "auth_context_ref": "auth-context://employee-session",
    }
    values.update(overrides)
    return RobotCompilationScope(**values)


def approved(
    *,
    kind: RobotKind = RobotKind.API,
    manifest: dict[str, str] | None = None,
    **overrides,
) -> ApprovedRobotVersion:
    if manifest is None:
        manifest = {
            "method": "GET",
            "url": "https://api.acme.example/v2/reports/daily",
            "operation_id": "getDailyReportV2",
        }
    values = {
        "tenant_id": "00000000-0000-4000-8000-0000000000a1",
        "company_id": "company-a",
        "objective_id": "daily-report",
        "robot_id": "daily-report-download",
        "robot_version": 8,
        "parent_version": None,
        "parent_version_fingerprint": None,
        "kind": kind,
        "semantic_intent": "download-daily-report",
        "capability_ref": "reports.download",
        "manifest": tuple(sorted(manifest.items())),
        "expected_outcome_fingerprint": OUTCOME,
        "source_robot_fingerprint": SOURCE,
        "candidate_fingerprint": CANDIDATE,
        "registry_candidate_fingerprint": REGISTRY_CANDIDATE,
        "approval_evidence_ref": "approval://robot-registry/review-123",
        "generation": 3,
        "registry_state": "active",
    }
    values.update(overrides)
    fingerprint = calculate_version_fingerprint(
        tenant_id=values["tenant_id"],
        company_id=values["company_id"],
        objective_id=values["objective_id"],
        robot_id=values["robot_id"],
        robot_version=values["robot_version"],
        parent_version=values["parent_version"],
        parent_version_fingerprint=values["parent_version_fingerprint"],
        kind=values["kind"],
        semantic_intent=values["semantic_intent"],
        capability_ref=values["capability_ref"],
        manifest=dict(values["manifest"]),
        expected_outcome_fingerprint=values["expected_outcome_fingerprint"],
        source_robot_fingerprint=values["source_robot_fingerprint"],
        candidate_fingerprint=values["candidate_fingerprint"],
        registry_candidate_fingerprint=values["registry_candidate_fingerprint"],
        approval_evidence_ref=values["approval_evidence_ref"],
    )
    values.setdefault("version_fingerprint", fingerprint)
    values.setdefault("active_version_fingerprint", values["version_fingerprint"])
    return ApprovedRobotVersion(**values)


def test_active_api_robot_compiles_to_passive_api_plan():
    compiled = compile_approved_robot(version=approved(), scope=scope())

    assert compiled.kind is CompiledPlanKind.API
    assert compiled.api_plan is not None
    assert compiled.api_plan.method == "GET"
    assert compiled.api_plan.operation_id == "getDailyReportV2"
    assert compiled.api_plan.direct_api_execution_authorized is False
    assert compiled.execution_authority_granted is False
    assert compiled.production_activation_granted is False


def test_non_get_api_is_tagged_possible_side_effect_but_not_authorized():
    version = approved(
        manifest={
            "method": "POST",
            "url": "https://api.acme.example/v2/reports/export",
            "operation_id": "createExport",
        }
    )
    compiled = compile_approved_robot(version=version, scope=scope())

    assert compiled.api_plan is not None
    assert compiled.api_plan.side_effect_possible is True
    assert compiled.api_plan.direct_api_execution_authorized is False
    assert compiled.execution_authority_granted is False


@pytest.mark.parametrize(
    ("url", "match"),
    [
        ("http://api.acme.example/v2/reports/daily", "not_trusted_https"),
        ("https://evil.example/v2/reports/daily", "not_trusted_https"),
        ("https://user:pass@api.acme.example/v2/reports/daily", "not_trusted_https"),
    ],
)
def test_api_compiler_rejects_untrusted_endpoint(url, match):
    version = approved(
        manifest={
            "method": "GET",
            "url": url,
            "operation_id": "getDailyReportV2",
        }
    )
    with pytest.raises(ValueError, match=match):
        compile_approved_robot(version=version, scope=scope())


def test_sensitive_manifest_field_is_rejected_even_on_approved_artifact():
    version = approved(
        manifest={
            "method": "GET",
            "url": "https://api.acme.example/v2/reports/daily",
            "operation_id": "getDailyReportV2",
            "authorization": "Bearer should-never-be-retained",
        }
    )
    with pytest.raises(ValueError, match="sensitive_field"):
        compile_approved_robot(version=version, scope=scope())


def test_api_manifest_must_be_exact_not_arbitrary_extension():
    version = approved(
        manifest={
            "method": "GET",
            "url": "https://api.acme.example/v2/reports/daily",
            "operation_id": "getDailyReportV2",
            "debug_script": "do-something",
        }
    )
    with pytest.raises(ValueError, match="api_manifest_not_exact"):
        compile_approved_robot(version=version, scope=scope())


def test_playwright_robot_compiles_to_existing_capability_plan():
    version = approved(
        kind=RobotKind.PLAYWRIGHT,
        manifest={
            "start_url": "https://portal.acme.example/reports/daily",
            "action_kind": "click",
            "action_id": "export-report",
            "commit_action_id": "export-report",
            "role": "button",
            "label": "Download Excel",
            "spatial_hint": "overflow-menu",
        },
        semantic_intent="export-excel",
        capability_ref="reports.export",
    )
    compiled = compile_approved_robot(version=version, scope=scope())

    assert compiled.kind is CompiledPlanKind.PLAYWRIGHT
    assert compiled.playwright_plan is not None
    assert compiled.playwright_plan.commit_action_id == "export-report"
    action = compiled.playwright_plan.actions[0]
    assert action.kind is BrowserActionKind.CLICK
    assert action.locator.kind is LocatorKind.ROLE
    assert action.locator.value == "button"
    assert action.locator.accessible_name == "Download Excel"
    assert "overflow-menu" not in action.model_dump_json()
    assert compiled.execution_authority_granted is False


def test_playwright_css_locator_is_not_compiled_from_registry():
    version = approved(
        kind=RobotKind.PLAYWRIGHT,
        manifest={
            "start_url": "https://portal.acme.example/reports/daily",
            "action_kind": "click",
            "action_id": "export-report",
            "commit_action_id": "export-report",
            "locator_kind": "css",
            "locator_value": "#export",
        },
    )
    with pytest.raises(ValueError, match="does_not_compile_css"):
        compile_approved_robot(version=version, scope=scope())


def test_playwright_v1_does_not_persist_fill_values_or_keys():
    version = approved(
        kind=RobotKind.PLAYWRIGHT,
        manifest={
            "start_url": "https://portal.acme.example/reports/daily",
            "action_kind": "fill",
            "action_id": "enter-secret",
            "commit_action_id": "enter-secret",
            "label": "Password",
        },
    )
    with pytest.raises(ValueError, match="only_compiles_click"):
        compile_approved_robot(version=version, scope=scope())


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("tenant_id", "00000000-0000-4000-8000-0000000000b1", "tenant_mismatch"),
        ("company_id", "company-b", "company_mismatch"),
        ("objective_id", "other-objective", "objective_mismatch"),
    ],
)
def test_cross_scope_compile_is_rejected(field, value, match):
    compile_scope = scope(**{field: value})
    with pytest.raises(ValueError, match=match):
        compile_approved_robot(version=approved(), scope=compile_scope)


def test_inactive_registry_artifact_is_rejected_at_model_boundary():
    with pytest.raises(ValidationError, match="requires_active_registry"):
        approved(registry_state="registered")


def test_active_pointer_fingerprint_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="active_fingerprint_mismatch"):
        approved(active_version_fingerprint="e" * 64)


def test_version_artifact_fingerprint_tampering_is_rejected():
    with pytest.raises(ValidationError, match="version_fingerprint_mismatch"):
        approved(version_fingerprint="f" * 64, active_version_fingerprint="f" * 64)


def test_hybrid_robot_requires_explicit_future_composition():
    version = approved(
        kind=RobotKind.HYBRID,
        manifest={"method": "GET", "url": "https://api.acme.example/v1/x", "operation_id": "x"},
    )
    with pytest.raises(ValueError, match="hybrid_plan_requires_explicit_composition"):
        compile_approved_robot(version=version, scope=scope())
