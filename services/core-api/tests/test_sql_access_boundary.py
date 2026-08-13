"""Fail-closed SQL/data-access architecture guard.

Any new runtime SQL execution path must be explicitly security-reviewed and
added to ALLOWED_SQL_EXECUTION_POINTS. Approved functions also have fixed
execution-call counts so reviewed SQL-capable functions cannot silently grow.
"""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

PLATFORM_RUNTIME_SQL_EXECUTION_POINTS = {
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

# Explicitly reviewed Academy SQL boundary. New Academy repository functions
# remain denied by default until deliberately added here and to the call-count
# registry below.
ACADEMY_RUNTIME_SQL_EXECUTION_POINTS = {
    ("modules/academy/rag.py", "grounded_document_answer"),
    ("modules/academy/repository.py", "record_learning_event"),
    ("modules/academy/repository.py", "record_platform_audit"),
    ("modules/academy/repository_catalog.py", "list_entitled_content"),
    ("modules/academy/repository_catalog.py", "get_media_asset"),
    ("modules/academy/repository_catalog.py", "list_checkpoints"),
    ("modules/academy/repository_catalog.py", "get_quiz_public_definition"),
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

PRIVILEGED_ADMIN_SQL_POINTS = {
    ("cli/bootstrap_access.py", "bootstrap"),
    ("cli/sync_backup_role_password.py", "synchronize"),
}

ALLOWED_SQL_EXECUTION_POINTS = (
    PLATFORM_RUNTIME_SQL_EXECUTION_POINTS
    | ACADEMY_RUNTIME_SQL_EXECUTION_POINTS
    | PRIVILEGED_ADMIN_SQL_POINTS
)

RUNTIME_ENGINE_CREATION = {
    ("core/resources.py", "<module>"),
    ("db/session.py", "<module>"),
}
PRIVILEGED_ENGINE_CREATION = PRIVILEGED_ADMIN_SQL_POINTS
ALLOWED_ENGINE_CREATION = RUNTIME_ENGINE_CREATION | PRIVILEGED_ENGINE_CREATION

EXECUTION_CALLS = {
    "execute", "exec_driver_sql", "executemany", "scalar", "scalars",
    "fetch", "fetchrow", "fetchval", "stream", "stream_scalars",
}
ENGINE_CALLS = {"create_engine", "create_async_engine"}


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


def _python_trees():
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig", errors="ignore")
        yield relative, ast.parse(source)


def test_runtime_sql_execution_is_fail_closed() -> None:
    violations: list[str] = []
    for relative, tree in _python_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if not name:
                continue
            location = (relative, _enclosing_function(tree, node))
            if name in EXECUTION_CALLS and location not in ALLOWED_SQL_EXECUTION_POINTS:
                violations.append(f"{relative}:{node.lineno} {location[1]} -> {name}")
            if name in ENGINE_CALLS and location not in ALLOWED_ENGINE_CREATION:
                violations.append(f"{relative}:{node.lineno} {location[1]} -> {name}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"asyncpg", "psycopg", "psycopg2", "pg8000"}:
                        violations.append(f"{relative}:{node.lineno} direct database driver import")
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".", 1)[0] in {"asyncpg", "psycopg", "psycopg2", "pg8000"}:
                    violations.append(f"{relative}:{node.lineno} direct database driver import")

    assert not violations, (
        "SECURE SQL BOUNDARY VIOLATION. New runtime database access is denied by default. "
        "Route it through the reviewed data-access boundary and explicitly security-review "
        "the new execution point:\n" + "\n".join(sorted(violations))
    )


def test_privileged_admin_sql_uses_migration_identity() -> None:
    violations: list[str] = []
    for relative in sorted({"cli/bootstrap_access.py", "cli/sync_backup_role_password.py"}):
        tree = ast.parse((APP_ROOT / relative).read_text(encoding="utf-8-sig", errors="ignore"))
        identifiers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            if isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
        if "migration_database_url" not in identifiers:
            violations.append(f"{relative} does not use migration_database_url")
        if "database_url" in identifiers:
            violations.append(f"{relative} references runtime database_url")
    assert not violations, "PRIVILEGED SQL IDENTITY VIOLATION:\n" + "\n".join(sorted(violations))


EXPECTED_EXECUTION_CALL_COUNTS = {
    ("core/resources.py", "check_database"): 1,
    ("core/resources.py", "ensure_audit_table"): 1,
    ("core/resources.py", "write_audit_event"): 2,
    ("core/resources.py", "list_audit_events"): 2,
    ("core/resources.py", "resolve_principal_access"): 2,
    ("core/resources.py", "resolve_membership_access"): 2,
    ("core/resources.py", "resolve_external_identity_membership"): 2,
    ("core/resources.py", "update_tenant_display_name"): 2,
    ("core/resources.py", "get_tenant"): 2,
    ("core/resources.py", "list_tenant_roles"): 2,
    ("core/resources.py", "create_tenant_member"): 4,
    ("core/resources.py", "update_tenant_member_access"): 9,
    ("core/resources.py", "list_tenant_members"): 2,
    ("db/session.py", "apply_tenant_context"): 2,
    ("cli/bootstrap_access.py", "bootstrap"): 7,
    ("cli/sync_backup_role_password.py", "synchronize"): 3,
    ("modules/academy/rag.py", "grounded_document_answer"): 1,
    ("modules/academy/repository.py", "record_learning_event"): 1,
    ("modules/academy/repository.py", "record_platform_audit"): 1,
    ("modules/academy/repository_catalog.py", "list_entitled_content"): 1,
    ("modules/academy/repository_catalog.py", "get_media_asset"): 1,
    ("modules/academy/repository_catalog.py", "list_checkpoints"): 1,
    ("modules/academy/repository_catalog.py", "get_quiz_public_definition"): 2,
    ("modules/academy/repository_certificate.py", "get_required_quiz_ids"): 1,
    ("modules/academy/repository_certificate.py", "is_completion_revoked"): 1,
    ("modules/academy/repository_certificate.py", "revoke_completion"): 2,
    ("modules/academy/repository_completion.py", "get_completion_snapshot"): 5,
    ("modules/academy/repository_completion.py", "mark_enrollment_completed"): 3,
    ("modules/academy/repository_content.py", "_insert_version"): 1,
    ("modules/academy/repository_content.py", "create_content"): 1,
    ("modules/academy/repository_content.py", "create_content_version"): 1,
    ("modules/academy/repository_content.py", "create_media_asset"): 1,
    ("modules/academy/repository_enrollment.py", "create_manual_enrollment"): 1,
    ("modules/academy/repository_enrollment.py", "reconcile_role_enrollments"): 1,
    ("modules/academy/repository_enrollment.py", "list_enrollments"): 1,
    ("modules/academy/repository_entitlement.py", "is_module_entitled"): 1,
    ("modules/academy/repository_idempotency_claim.py", "claim_idempotency_key"): 2,
    ("modules/academy/repository_knowledge.py", "ingest_document_chunks"): 3,
    ("modules/academy/repository_path.py", "create_learning_path"): 3,
    ("modules/academy/repository_path.py", "grant_entitlement"): 1,
    ("modules/academy/repository_progress.py", "get_progress_target"): 1,
    ("modules/academy/repository_progress.py", "get_blocking_checkpoint"): 1,
    ("modules/academy/repository_progress.py", "save_progress"): 3,
    ("modules/academy/repository_progress.py", "get_progress_snapshot"): 1,
    ("modules/academy/repository_quiz.py", "get_quiz_definition_for_attempt"): 3,
    ("modules/academy/repository_quiz.py", "save_quiz_attempt"): 2,
    ("modules/academy/repository_quiz.py", "get_quiz_attempt_by_id"): 1,
    ("modules/academy/repository_quiz_authoring.py", "create_quiz"): 5,
}


def test_approved_sql_functions_cannot_grow_silently() -> None:
    discovered: dict[tuple[str, str], int] = {}
    for relative, tree in _python_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in EXECUTION_CALLS:
                key = (relative, _enclosing_function(tree, node))
                discovered[key] = discovered.get(key, 0) + 1
    mismatches = [
        f"{key[0]}::{key[1]} expected={expected} actual={discovered.get(key, 0)}"
        for key, expected in sorted(EXPECTED_EXECUTION_CALL_COUNTS.items())
        if discovered.get(key, 0) != expected
    ]
    assert not mismatches, (
        "APPROVED SQL FUNCTION CHANGED. Existing SQL-capable functions may not gain or lose "
        "database execution calls without explicit security review:\n" + "\n".join(mismatches)
    )


def test_raw_sql_text_must_be_static_literal() -> None:
    violations: list[str] = []
    for relative, tree in _python_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name == "text":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    violations.append(f"{relative}:{node.lineno} dynamic text() SQL")
            if name in {"exec_driver_sql", "executemany"}:
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    violations.append(f"{relative}:{node.lineno} dynamic {name}() SQL")
    assert not violations, (
        "DYNAMIC RAW SQL IS FORBIDDEN. SQL structure must be a static reviewed literal; "
        "all runtime values must use bound parameters:\n" + "\n".join(sorted(violations))
    )


def test_execution_sql_sources_are_static_reviewed() -> None:
    violations: list[str] = []

    def source_is_static(node: ast.AST, assignments: dict[str, list[ast.AST]], seen: set[str] | None = None) -> bool:
        seen = set() if seen is None else set(seen)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return True
        if isinstance(node, ast.Call):
            return (
                _call_name(node) == "text"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            )
        if isinstance(node, ast.Name):
            if node.id in seen:
                return False
            sources = assignments.get(node.id, [])
            return bool(sources) and all(
                source_is_static(source, assignments, seen | {node.id}) for source in sources
            )
        return False

    for relative, tree in _python_trees():
        functions = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for function in functions:
            assignments: dict[str, list[ast.AST]] = {}
            for node in ast.walk(function):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assignments.setdefault(target.id, []).append(node.value)
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                    assignments.setdefault(node.target.id, []).append(node.value)
            for node in ast.walk(function):
                if not isinstance(node, ast.Call) or _call_name(node) not in EXECUTION_CALLS:
                    continue
                method = _call_name(node)
                if not node.args:
                    violations.append(
                        f"{relative}:{node.lineno} {function.name}::{method} has no reviewed SQL source"
                    )
                    continue
                if not source_is_static(node.args[0], assignments):
                    violations.append(
                        f"{relative}:{node.lineno} {function.name}::{method} uses non-static SQL provenance"
                    )
    assert not violations, (
        "UNREVIEWED SQL SOURCE DETECTED. Database execution must originate from a static reviewed "
        "SQL literal. Runtime values may never construct SQL structure:\n" + "\n".join(sorted(violations))
    )


def test_sql_execution_allowlist_has_no_stale_entries() -> None:
    discovered: set[tuple[str, str]] = set()
    for relative, tree in _python_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in EXECUTION_CALLS:
                discovered.add((relative, _enclosing_function(tree, node)))
    stale = ALLOWED_SQL_EXECUTION_POINTS - discovered
    assert not stale, "SQL boundary allowlist contains stale entries: " + repr(sorted(stale))
