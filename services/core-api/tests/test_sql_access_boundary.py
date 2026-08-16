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
    ("modules/budget/procurement.py", "create_request"),
    ("modules/budget/procurement.py", "decide_request"),
    ("modules/budget/procurement.py", "create_po"),
    ("modules/budget/read_models.py", "variance_summary"),
    ("modules/budget/read_models.py", "financial_events"),
}

ACADEMY_SQL_EXECUTION_POINTS = {
    ("modules/academy/rag.py", "grounded_document_answer"),
    ("modules/academy/repository.py", "record_learning_event"),
    # Product read models below were security-reviewed on 2026-08-14:
    # every query is static SQL and carries tenant_id; learner workspace and
    # certificate queries also bind the authenticated subject. No wildcard
    # repository/module allowlisting is permitted here.
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
    ("modules/academy/repository_enrollment.py", "create_manual_enrollment"),
    ("modules/academy/repository_enrollment.py", "reconcile_role_enrollments"),
    ("modules/academy/repository_enrollment.py", "list_enrollments"),
    ("modules/academy/repository_enrollment.py", "get_enrollment_workspace"),
    ("modules/academy/repository_entitlement.py", "is_module_entitled"),
    ("modules/academy/repository_idempotency_claim.py", "claim_idempotency_key"),
    ("modules/academy/repository_knowledge.py", "ingest_document_chunks"),
    ("modules/academy/repository_path.py", "create_learning_path"),
    ("modules/academy/repository_path.py", "grant_entitlement"),
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
    # Security-reviewed on 2026-08-16 for item 4/60. SQL text is static,
    # values are bound parameters, each transaction sets app.tenant_id, and
    # migration 0019 enables + forces tenant RLS with USING/WITH CHECK.
    ("modules/field_intelligence/repository.py", "_set_tenant"),
    ("modules/field_intelligence/repository.py", "upsert_location"),
    ("modules/field_intelligence/repository.py", "list_locations"),
    ("modules/field_intelligence/repository.py", "list_templates"),
    ("modules/field_intelligence/repository.py", "create_template"),
    ("modules/field_intelligence/repository.py", "create_mission"),
    ("modules/field_intelligence/repository.py", "list_missions"),
}

ALLOWED_SQL_EXECUTION_POINTS = (
    RUNTIME_SQL_EXECUTION_POINTS
    | PRIVILEGED_ADMIN_SQL_POINTS
    | BUDGET_SQL_EXECUTION_POINTS
    | ACADEMY_SQL_EXECUTION_POINTS
    | FIELD_INTELLIGENCE_SQL_EXECUTION_POINTS
)

RUNTIME_ENGINE_CREATION = {
    ("core/resources.py", "<module>"),
    ("db/session.py", "<module>"),
}

PRIVILEGED_ENGINE_CREATION = {
    ("cli/bootstrap_access.py", "bootstrap"),
    ("cli/sync_backup_role_password.py", "synchronize"),
}

ALLOWED_ENGINE_CREATION = (
    RUNTIME_ENGINE_CREATION
    | PRIVILEGED_ENGINE_CREATION
)

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

ENGINE_CALLS = {
    "create_engine",
    "create_async_engine",
}

DIRECT_DRIVER_CALLS = {
    "connect",
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id

    if isinstance(node.func, ast.Attribute):
        return node.func.attr

    return None


def _enclosing_function(
    tree: ast.AST,
    target: ast.AST,
) -> str:
    result = "<module>"

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def generic_visit(self, node: ast.AST) -> None:
            nonlocal result

            is_function = isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )

            if is_function:
                self.stack.append(node.name)

            if node is target:
                result = (
                    self.stack[-1]
                    if self.stack
                    else "<module>"
                )

            super().generic_visit(node)

            if is_function:
                self.stack.pop()

    Visitor().visit(tree)
    return result


def test_runtime_sql_execution_is_fail_closed() -> None:
    violations: list[str] = []

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()

        source = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = _call_name(node)

            if not name:
                continue

            function = _enclosing_function(
                tree,
                node,
            )

            location = (
                relative,
                function,
            )

            if (
                name in EXECUTION_CALLS
                and location not in ALLOWED_SQL_EXECUTION_POINTS
            ):
                violations.append(
                    f"{relative}:{node.lineno} "
                    f"{function} -> {name}"
                )

            if (
                name in ENGINE_CALLS
                and location not in ALLOWED_ENGINE_CREATION
            ):
                violations.append(
                    f"{relative}:{node.lineno} "
                    f"{function} -> {name}"
                )

        # Direct DB drivers may only exist behind the approved
        # SQLAlchemy/session boundary. This intentionally blocks
        # future asyncpg/psycopg shortcuts.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import):
                continue

            for alias in node.names:
                if alias.name in {
                    "asyncpg",
                    "psycopg",
                    "psycopg2",
                    "pg8000",
                }:
                    violations.append(
                        f"{relative}:{node.lineno} "
                        "direct database driver import"
                    )

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue

            module = node.module or ""

            if module.split(".", 1)[0] in {
                "asyncpg",
                "psycopg",
                "psycopg2",
                "pg8000",
            }:
                violations.append(
                    f"{relative}:{node.lineno} "
                    "direct database driver import"
                )

    assert not violations, (
        "SECURE SQL BOUNDARY VIOLATION. "
        "New runtime database access is denied by default. "
        "Route it through the reviewed data-access boundary "
        "and explicitly security-review the new execution point:\n"
        + "\n".join(sorted(violations))
    )


def test_approved_sql_functions_cannot_grow_silently() -> None:
    current_locations: set[tuple[str, str]] = set()

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = _call_name(node)

            if name not in EXECUTION_CALLS:
                continue

            current_locations.add(
                (
                    relative,
                    _enclosing_function(tree, node),
                )
            )

    assert current_locations == ALLOWED_SQL_EXECUTION_POINTS, (
        "SQL execution allowlist drift detected. "
        f"added={sorted(current_locations - ALLOWED_SQL_EXECUTION_POINTS)} "
        f"removed={sorted(ALLOWED_SQL_EXECUTION_POINTS - current_locations)}"
    )


def test_raw_sql_text_must_be_static_literal() -> None:
    violations: list[str] = []

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if _call_name(node) != "text":
                continue

            if not node.args:
                violations.append(
                    f"{relative}:{node.lineno} text() with no argument"
                )
                continue

            first = node.args[0]

            if not (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                violations.append(
                    f"{relative}:{node.lineno} dynamic text() SQL"
                )

    assert not violations, (
        "DYNAMIC SQL DENIED. All SQLAlchemy text() statements "
        "must be static literals with bound parameters:\n"
        + "\n".join(sorted(violations))
    )


def test_execution_sql_sources_are_static_reviewed() -> None:
    violations: list[str] = []

    for relative, function in sorted(ALLOWED_SQL_EXECUTION_POINTS):
        path = APP_ROOT / relative
        source = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )
        tree = ast.parse(source)

        matched = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) not in EXECUTION_CALLS:
                continue
            if _enclosing_function(tree, node) != function:
                continue

            matched = True

        if not matched:
            violations.append(
                f"{relative}:{function} has no SQL execution"
            )

    assert not violations, (
        "STALE/INVALID SQL EXECUTION ALLOWLIST:\n"
        + "\n".join(sorted(violations))
    )


def test_engine_creation_is_fail_closed() -> None:
    violations: list[str] = []

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if _call_name(node) not in ENGINE_CALLS:
                continue

            location = (
                relative,
                _enclosing_function(tree, node),
            )

            if location not in ALLOWED_ENGINE_CREATION:
                violations.append(
                    f"{relative}:{node.lineno} {location[1]}"
                )

    assert not violations, (
        "NEW DATABASE ENGINE CREATION DENIED:\n"
        + "\n".join(sorted(violations))
    )


def test_sql_execution_allowlist_has_no_stale_entries() -> None:
    for relative, function in ALLOWED_SQL_EXECUTION_POINTS:
        path = APP_ROOT / relative
        assert path.exists(), relative

        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        )

        function_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        if function != "<module>":
            assert function in function_names, (
                relative,
                function,
            )
