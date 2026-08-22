"""Fail-closed SQL/data-access architecture guard.

Any new runtime SQL execution path must be explicitly security-reviewed
and added to ALLOWED_SQL_EXECUTION_POINTS.

This deliberately makes future AI-generated SQL, analytics endpoints,
ad-hoc query services, or direct DB access fail CI by default.
"""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

RUNTIME_SQL_EXECUTION_POINTS = {
    ("core/ai_data_scope_admin.py", "list_ai_data_scope_assignments"),
    ("core/ai_data_scope_admin.py", "_write_scope_change_audit_in_transaction"),
    ("core/ai_data_scope_admin.py", "update_ai_data_scope_assignment"),
    ("core/ai_tenant_query_context.py", "get_ai_tenant_query_context"),
    ("core/ai_tenant_query_context.py", "_write_query_context_audit_in_transaction"),
    ("core/ai_tenant_query_context.py", "put_ai_tenant_query_context"),
    ("core/audit.py", "write_transactional_audit_event"),
    ("core/resources.py", "check_database"),
    ("core/resources.py", "ensure_audit_table"),
    ("core/resources.py", "write_audit_event"),
    ("core/resources.py", "list_audit_events"),
    ("core/resources.py", "resolve_principal_access"),
    ("core/resources.py", "resolve_membership_access"),
    ("core/resources.py", "resolve_external_identity_membership"),
    ("core/resources.py", "resolve_preauth_oidc_providers"),
    ("core/resources.py", "update_tenant_display_name"),
    ("core/resources.py", "get_tenant"),
    ("core/resources.py", "list_tenant_roles"),
    ("core/resources.py", "create_tenant_member"),
    ("core/resources.py", "update_tenant_member_access"),
    ("core/resources.py", "list_tenant_members"),
    ("db/session.py", "apply_tenant_context"),
}

PRIVILEGED_ADMIN_SQL_POINTS = {
    ("cli/bootstrap_access.py", "bootstrap"),
    ("cli/sync_backup_role_password.py", "synchronize"),
}

BUDGET_SQL_EXECUTION_POINTS = {
    ("modules/budget/commands.py", "run_command"),
    ("modules/budget/evidence.py", "emit_financial_event"),
    ("modules/budget/imports.py", "stage_import"),
    ("modules/budget/ledger.py", "post_invoice"),
    ("modules/budget/ledger.py", "resolve_reconciliation"),
    ("modules/budget/permissions.py", "dependency"),
    ("modules/budget/planning.py", "create_plan"),
    ("modules/budget/planning.py", "activate_plan"),
    ("modules/budget/planning.py", "create_period"),
    ("modules/budget/planning.py", "create_cost_center"),
    ("modules/budget/planning.py", "create_line"),
    ("modules/budget/planning.py", "create_forecast"),
    ("modules/budget/planning.py", "close_period"),
    # Master 28/60 security review: scenario/assumption/driver/allocation SQL is
    # static text() with bound parameters only. Runtime authorization still
    # flows through BudgetUnitOfWork tenant and cost-center scope authority.
    ("modules/budget/planning_engine.py", "create_scenario"),
    ("modules/budget/planning_engine.py", "add_assumption"),
    ("modules/budget/planning_engine.py", "add_driver_line"),
    ("modules/budget/planning_engine.py", "add_allocation_rule"),
    ("modules/budget/planning_engine.py", "publish_scenario"),
    ("modules/budget/planning_engine.py", "get_activation_snapshot"),
    ("modules/budget/planning_engine.py", "list_scenarios"),
    ("modules/budget/procurement.py", "create_request"),
    ("modules/budget/procurement.py", "decide_request"),
    ("modules/budget/procurement.py", "create_po"),
    ("modules/budget/read_models.py", "variance_summary"),
    ("modules/budget/read_models.py", "financial_events"),
}

ACADEMY_SQL_EXECUTION_POINTS = {
    ("modules/academy/rag.py", "grounded_document_answer"),
    ("modules/academy/repository.py", "record_learning_event"),
    ("modules/academy/repository_admin.py", "list_admin_content"),
    ("modules/academy/repository_admin.py", "list_admin_paths"),
    ("modules/academy/repository_admin.py", "academy_admin_summary"),
    ("modules/academy/repository_catalog.py", "list_entitled_content"),
    ("modules/academy/repository_catalog.py", "get_media_asset"),
    ("modules/academy/repository_catalog.py", "list_checkpoints"),
    ("modules/academy/repository_catalog.py", "get_quiz_public_definition"),
    ("modules/academy/repository_certificate.py", "list_certificates"),
    ("modules/academy/repository_certificate.py", "get_required_quiz_ids"),
    ("modules/academy/repository_certificate.py", "is_completion_revoked"),
    ("modules/academy/repository_certificate.py", "revoke_completion"),
    ("modules/academy/repository_completion.py", "get_completion_snapshot"),
    ("modules/academy/repository_completion.py", "mark_enrollment_completed"),
    ("modules/academy/repository_content.py", "_insert_version"),
    ("modules/academy/repository_content.py", "create_content"),
    ("modules/academy/repository_content.py", "create_content_version"),
    ("modules/academy/repository_content.py", "create_media_asset"),
    # Academy credential authority security review: exact functions only.
    # SQL is static text() with bound parameters, tenant selection is principal-bound,
    # and migration 0050 enforces FORCE RLS plus append-only credential evidence.
    ("modules/academy/repository_credentials.py", "create_badge_definition"),
    ("modules/academy/repository_credentials.py", "retire_badge_definition"),
    ("modules/academy/repository_credentials.py", "issue_badge_award"),
    ("modules/academy/repository_credentials.py", "revoke_badge_award"),
    ("modules/academy/repository_credentials.py", "list_my_badge_credentials"),
    ("modules/academy/repository_credentials.py", "get_my_badge_credential"),
    ("modules/academy/repository_enrollment.py", "create_manual_enrollment"),
    ("modules/academy/repository_enrollment.py", "reconcile_role_enrollments"),
    ("modules/academy/repository_enrollment.py", "list_enrollments"),
    ("modules/academy/repository_enrollment.py", "get_enrollment_workspace"),
    ("modules/academy/repository_entitlement.py", "is_module_entitled"),
    ("modules/academy/repository_experience.py", "create_interaction_set"),
    ("modules/academy/repository_experience.py", "get_interaction_timeline"),
    ("modules/academy/repository_experience.py", "create_scenario"),
    ("modules/academy/repository_experience.py", "_scenario_runtime_view"),
    ("modules/academy/repository_experience.py", "start_scenario_run"),
    ("modules/academy/repository_experience.py", "apply_scenario_decision"),
    ("modules/academy/repository_idempotency_claim.py", "claim_idempotency_key"),
    ("modules/academy/repository_knowledge.py", "ingest_document_chunks"),
    ("modules/academy/repository_localization.py", "list_locale_settings"),
    ("modules/academy/repository_localization.py", "upsert_locale_setting"),
    ("modules/academy/repository_localization.py", "create_translation_lineage"),
    ("modules/academy/repository_localization.py", "submit_translation"),
    ("modules/academy/repository_localization.py", "review_translation"),
    ("modules/academy/repository_localization.py", "list_translation_authority"),
    ("modules/academy/repository_path.py", "create_learning_path"),
    ("modules/academy/repository_path.py", "grant_entitlement"),
    ("modules/academy/repository_playback.py", "create_playback_session"),
    ("modules/academy/repository_playback.py", "get_playback_session_for_update"),
    ("modules/academy/repository_playback.py", "commit_playback_heartbeat"),
    ("modules/academy/repository_playback.py", "get_verified_playback_snapshot"),
    ("modules/academy/repository_playback.py", "close_playback_session"),
    ("modules/academy/repository_progress.py", "get_progress_target"),
    ("modules/academy/repository_progress.py", "get_blocking_checkpoint"),
    ("modules/academy/repository_progress.py", "save_progress"),
    ("modules/academy/repository_progress.py", "get_progress_snapshot"),
    ("modules/academy/repository_quiz.py", "get_quiz_definition_for_attempt"),
    ("modules/academy/repository_quiz.py", "save_quiz_attempt"),
    ("modules/academy/repository_quiz.py", "get_quiz_attempt_by_id"),
    ("modules/academy/repository_quiz_authoring.py", "create_quiz"),
}

FIELD_INTELLIGENCE_SQL_EXECUTION_POINTS = {
    ("modules/field_intelligence/repository.py", "_set_tenant"),
    ("modules/field_intelligence/repository.py", "upsert_location"),
    ("modules/field_intelligence/repository.py", "list_locations"),
    ("modules/field_intelligence/repository.py", "list_templates"),
    ("modules/field_intelligence/repository.py", "create_template"),
    ("modules/field_intelligence/repository.py", "create_mission"),
    ("modules/field_intelligence/repository.py", "list_missions"),
    ("modules/field_intelligence/repository.py", "get_mission_detail"),
    ("modules/field_intelligence/repository.py", "set_mission_status"),
    ("modules/field_intelligence/repository.py", "submit_evidence"),
    ("modules/field_intelligence/repository.py", "list_evidence"),
    ("modules/field_intelligence/repository.py", "review_evidence"),
    ("modules/field_intelligence/repository.py", "queue_notification_intents"),
    ("modules/field_intelligence/repository.py", "field_analytics"),
    # Item 9/60 security review: static SQL + bound parameters, canonical
    # app.tenant_id context, FORCE RLS, append-only receipts/policy records,
    # deterministic replay and fail-closed attestation/object authority gates.
    ("modules/field_intelligence/mobile_offline.py", "set_template_evidence_policy"),
    ("modules/field_intelligence/mobile_offline.py", "_sync_one"),
    ("modules/field_intelligence/evidence_integrity.py", "_device_authority_fingerprint"),
    ("modules/field_intelligence/evidence_integrity.py", "verify_evidence_authority"),
    ("modules/field_intelligence/evidence_object_upload.py", "_authorize_upload"),
    ("modules/field_intelligence/evidence_object_upload.py", "_existing_receipt"),
    ("modules/field_intelligence/evidence_object_upload.py", "upload_private_evidence_object"),
    # Items 7-10/60 governance security review: exact functions only. Every SQL
    # statement is a static text() literal with bound parameters, each transaction
    # enters canonical app.tenant_id context, and governed tables are FORCE-RLS.
    # Recurrence/exemption/export evidence is append-only and export is maker-checker.
    ("modules/field_intelligence/governance.py", "retire_template_version"),
    ("modules/field_intelligence/governance.py", "create_recurrence_rule"),
    ("modules/field_intelligence/governance.py", "list_recurrence_rules"),
    ("modules/field_intelligence/governance.py", "exempt_target"),
    ("modules/field_intelligence/governance.py", "preview_server_targeting"),
    ("modules/field_intelligence/governance.py", "request_export"),
    ("modules/field_intelligence/governance.py", "decide_export"),
    # Item 10/60 security review: Field promotion tables are RLS-bound and
    # append-only. These paths emit immutable candidate/decision/receipt evidence
    # and never update Inventory, Planogram or Budget authority tables.
    ("modules/field_intelligence/promotion.py", "create_promotion_request"),
    ("modules/field_intelligence/promotion.py", "list_promotion_requests"),
    ("modules/field_intelligence/promotion.py", "decide_promotion_request"),
    ("modules/field_intelligence/promotion.py", "record_consumer_receipt"),
    ("modules/field_intelligence/promotion_access.py", "get_promotion_authorization_context"),
    # Master 26/60: Planogram compliance uses the same governed Field promotion
    # tables. New adapter SQL is static/bound, latest accepted evidence only,
    # and transaction-local consumer receipt preserves atomic handoff.
    (
        "modules/field_intelligence/planogram_compliance_promotion.py",
        "create_planogram_compliance_promotion",
    ),
    (
        "modules/field_intelligence/promotion_consumer_session.py",
        "get_promotion_context_in_session",
    ),
    (
        "modules/field_intelligence/promotion_consumer_session.py",
        "record_consumer_receipt_in_session",
    ),
}

# Master 24-26/60 security review: Planogram SQL is static text() with bound
# parameters only. Runtime sessions enter canonical app.tenant_id context.
# 0030-0035 enforce FORCE RLS, immutable approved plan/Store DNA history,
# append-only compliance evidence, runtime attestation denial and immutable
# assignment identity. Cross-module compliance handoff is transaction-bound.
PLANOGRAM_SQL_EXECUTION_POINTS = {
    ("modules/planogram/repository_store_dna.py", "_record_store_dna_event"),
    ("modules/planogram/repository_store_dna.py", "list_store_dna_versions"),
    ("modules/planogram/repository_store_dna.py", "create_store_dna_draft"),
    ("modules/planogram/repository_store_dna.py", "update_store_dna_draft"),
    ("modules/planogram/repository_store_dna.py", "submit_store_dna"),
    ("modules/planogram/repository_store_dna.py", "approve_store_dna"),
    ("modules/planogram/repository_store_dna.py", "reject_store_dna"),
    ("modules/planogram/repository_store_dna.py", "revise_store_dna"),
    ("modules/planogram/repository_store_dna.py", "get_approved_store_dna"),
    ("modules/planogram/repository_execution.py", "_plan_event"),
    ("modules/planogram/repository_execution.py", "list_plan_versions"),
    ("modules/planogram/repository_execution.py", "create_plan_draft"),
    ("modules/planogram/repository_execution.py", "submit_plan"),
    ("modules/planogram/repository_execution.py", "approve_plan"),
    ("modules/planogram/repository_execution.py", "reject_plan"),
    ("modules/planogram/repository_execution.py", "_execution_event"),
    ("modules/planogram/repository_execution.py", "create_assignment"),
    ("modules/planogram/repository_execution.py", "acknowledge_assignment"),
    ("modules/planogram/repository_execution.py", "list_assignments"),
    ("modules/planogram/repository_execution.py", "get_assignment_plan"),
    ("modules/planogram/repository_execution.py", "insert_compliance_observation"),
    ("modules/planogram/repository_plan_edit.py", "update_plan_draft"),
    ("modules/planogram/repository_assignment_lifecycle.py", "close_assignment"),
}

# Jarvis control-plane security review: exact repository methods only.
# Statements are static text() literals with bound parameters. Every robot
# registry/lease query is exact-scope and transaction-bound; migrations 0051-0054
# enforce FORCE RLS, immutable evidence, generation fences and atomic stale-lease
# revocation when registry selection changes.
JARVIS_AGENT_SQL_EXECUTION_POINTS = {
    ("agent_job_repository.py", "create"),
    ("agent_job_repository.py", "get"),
    ("agent_job_repository.py", "events"),
    ("agent_job_repository.py", "cancel"),
    ("epistemic_rollout_repository.py", "get"),
    ("epistemic_rollout_repository.py", "_lock"),
    ("epistemic_rollout_repository.py", "activate"),
    ("epistemic_rollout_repository.py", "list_receipts"),
    ("epistemic_rollout_repository.py", "_insert_receipt"),
    ("epistemic_rollout_repository.py", "append_receipt"),
    ("epistemic_rollout_repository.py", "apply_rollback"),
    ("robot_registry_repository.py", "register_version"),
    ("robot_registry_repository.py", "activate_version"),
    ("robot_registry_repository.py", "rollback_version"),
    ("robot_registry_repository.py", "get"),
    ("robot_registry_repository.py", "get_version"),
    ("robot_registry_repository.py", "list_versions"),
    ("robot_registry_repository.py", "list_receipts"),
    ("robot_registry_repository.py", "_latest_version"),
    ("robot_registry_repository.py", "_lock"),
    ("robot_registry_repository.py", "_registration_receipt_for_version"),
    ("robot_registry_repository.py", "_latest_selection_receipt"),
    ("robot_registry_repository.py", "_append_receipt_locked"),
    ("robot_execution_lease_repository.py", "issue"),
    ("robot_execution_lease_repository.py", "complete"),
    ("robot_execution_lease_repository.py", "get"),
    ("robot_execution_lease_repository.py", "list_receipts"),
    ("robot_execution_lease_repository.py", "_active_registry_for_share"),
    ("robot_execution_lease_repository.py", "_revoke_locked"),
    ("robot_execution_lease_repository.py", "_append_receipt"),
    ("robot_execution_lease_repository.py", "_first_receipt"),
}

ALLOWED_SQL_EXECUTION_POINTS = (
    RUNTIME_SQL_EXECUTION_POINTS
    | PRIVILEGED_ADMIN_SQL_POINTS
    | BUDGET_SQL_EXECUTION_POINTS
    | ACADEMY_SQL_EXECUTION_POINTS
    | FIELD_INTELLIGENCE_SQL_EXECUTION_POINTS
    | PLANOGRAM_SQL_EXECUTION_POINTS
    | JARVIS_AGENT_SQL_EXECUTION_POINTS
)

RUNTIME_ENGINE_CREATION = {
    ("core/resources.py", "<module>"),
    ("db/session.py", "<module>"),
}

PRIVILEGED_ENGINE_CREATION = {
    ("cli/bootstrap_access.py", "bootstrap"),
    ("cli/sync_backup_role_password.py", "synchronize"),
}

ALLOWED_ENGINE_CREATION = RUNTIME_ENGINE_CREATION | PRIVILEGED_ENGINE_CREATION

EXECUTION_CALLS = {
    "execute",
    "exec_driver_sql",
    "executemany",
    "scalar",
    "scalars",
    "fetch",
    "fetchrow",
    "fetchval",
    "stream",
    "stream_scalars",
}

ENGINE_CALLS = {"create_engine", "create_async_engine"}
DIRECT_DRIVER_CALLS = {"connect"}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str:
    result = "<module>"

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def generic_visit(self, node: ast.AST) -> None:
            nonlocal result
            is_function = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            if is_function:
                self.stack.append(node.name)
            if node is target:
                result = self.stack[-1] if self.stack else "<module>"
            super().generic_visit(node)
            if is_function:
                self.stack.pop()

    Visitor().visit(tree)
    return result


def test_runtime_sql_execution_is_fail_closed() -> None:
    violations: list[str] = []

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig", errors="ignore")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if not name:
                continue
            function = _enclosing_function(tree, node)
            location = (relative, function)
            if name in EXECUTION_CALLS and location not in ALLOWED_SQL_EXECUTION_POINTS:
                violations.append(f"{relative}:{node.lineno} {function} -> {name}")
            if name in ENGINE_CALLS and location not in ALLOWED_ENGINE_CREATION:
                violations.append(f"{relative}:{node.lineno} {location[1]}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"asyncpg", "psycopg", "psycopg2", "pg8000"}:
                        violations.append(f"{relative}:{node.lineno} direct database driver import")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".", 1)[0] in {"asyncpg", "psycopg", "psycopg2", "pg8000"}:
                    violations.append(f"{relative}:{node.lineno} direct database driver import")

    assert not violations, (
        "SECURE SQL BOUNDARY VIOLATION. New runtime database access is denied by default. "
        "Route it through the reviewed data-access boundary and explicitly security-review "
        "the new execution point:\n" + "\n".join(sorted(violations))
    )


def test_approved_sql_functions_cannot_grow_silently() -> None:
    current_locations: set[tuple[str, str]] = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in EXECUTION_CALLS:
                current_locations.add((relative, _enclosing_function(tree, node)))

    assert current_locations == ALLOWED_SQL_EXECUTION_POINTS, (
        "SQL execution allowlist drift detected. "
        f"added={sorted(current_locations - ALLOWED_SQL_EXECUTION_POINTS)} "
        f"removed={sorted(ALLOWED_SQL_EXECUTION_POINTS - current_locations)}"
    )


def test_raw_sql_text_must_be_static_literal() -> None:
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) != "text":
                continue
            if not node.args:
                violations.append(f"{relative}:{node.lineno} text() with no argument")
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                violations.append(f"{relative}:{node.lineno} dynamic text() SQL")

    assert not violations, (
        "DYNAMIC SQL DENIED. All SQLAlchemy text() statements must be static literal "
        "with bound parameters:\n" + "\n".join(sorted(violations))
    )


def test_execution_sql_sources_are_static_reviewed() -> None:
    violations: list[str] = []
    for relative, function in sorted(ALLOWED_SQL_EXECUTION_POINTS):
        path = APP_ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
        matched = any(
            isinstance(node, ast.Call)
            and _call_name(node) in EXECUTION_CALLS
            and _enclosing_function(tree, node) == function
            for node in ast.walk(tree)
        )
        if not matched:
            violations.append(f"{relative}:{function} has no SQL execution")

    assert not violations, (
        "STALE/INVALID SQL EXECUTION ALLOWLIST:\n" + "\n".join(sorted(violations))
    )


def test_engine_creation_is_fail_closed() -> None:
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in ENGINE_CALLS:
                continue
            location = (relative, _enclosing_function(tree, node))
            if location not in ALLOWED_ENGINE_CREATION:
                violations.append(f"{relative}:{node.lineno} {location[1]}")

    assert not violations, "NEW DATABASE ENGINE CREATION DENIED:\n" + "\n".join(sorted(violations))


def test_sql_execution_allowlist_has_no_stale_entries() -> None:
    for relative, function in ALLOWED_SQL_EXECUTION_POINTS:
        path = APP_ROOT / relative
        assert path.exists(), relative
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
        function_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if function != "<module>":
            assert function in function_names, (relative, function)
