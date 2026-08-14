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

ALLOWED_SQL_EXECUTION_POINTS = (
    RUNTIME_SQL_EXECUTION_POINTS
    | PRIVILEGED_ADMIN_SQL_POINTS
    | BUDGET_SQL_EXECUTION_POINTS
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


def test_privileged_admin_sql_uses_migration_identity() -> None:
    violations: list[str] = []

    privileged_files = {
        "cli/bootstrap_access.py",
        "cli/sync_backup_role_password.py",
    }

    for relative in sorted(privileged_files):
        path = APP_ROOT / relative

        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        )

        identifiers: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)

            if isinstance(node, ast.Attribute):
                identifiers.add(node.attr)

        if "migration_database_url" not in identifiers:
            violations.append(
                f"{relative} does not use migration_database_url"
            )

        if "database_url" in identifiers:
            violations.append(
                f"{relative} references runtime database_url"
            )

    assert not violations, (
        "PRIVILEGED SQL IDENTITY VIOLATION:\n"
        + "\n".join(sorted(violations))
    )


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
    ("modules/budget/commands.py", "run_command"): 3,
    ("modules/budget/evidence.py", "emit_financial_event"): 3,
    ("modules/budget/imports.py", "stage_import"): 3,
    ("modules/budget/ledger.py", "post_invoice"): 6,
    ("modules/budget/ledger.py", "resolve_reconciliation"): 9,
    ("modules/budget/permissions.py", "dependency"): 1,
    ("modules/budget/planning.py", "create_plan"): 1,
    ("modules/budget/planning.py", "activate_plan"): 3,
    ("modules/budget/planning.py", "create_period"): 4,
    ("modules/budget/planning.py", "create_cost_center"): 1,
    ("modules/budget/planning.py", "create_line"): 3,
    ("modules/budget/planning.py", "create_forecast"): 1,
    ("modules/budget/planning.py", "close_period"): 3,
    ("modules/budget/procurement.py", "create_request"): 3,
    ("modules/budget/procurement.py", "decide_request"): 3,
    ("modules/budget/procurement.py", "create_po"): 4,
    ("modules/budget/read_models.py", "variance_summary"): 1,
    ("modules/budget/read_models.py", "financial_events"): 1,
}


def test_approved_sql_functions_cannot_grow_silently() -> None:
    discovered: dict[tuple[str, str], int] = {}

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

            if _call_name(node) not in EXECUTION_CALLS:
                continue

            function = _enclosing_function(tree, node)
            key = (relative, function)

            discovered[key] = discovered.get(key, 0) + 1

    mismatches: list[str] = []

    for key, expected in sorted(
        EXPECTED_EXECUTION_CALL_COUNTS.items()
    ):
        actual = discovered.get(key, 0)

        if actual != expected:
            mismatches.append(
                f"{key[0]}::{key[1]} "
                f"expected={expected} actual={actual}"
            )

    assert not mismatches, (
        "APPROVED SQL FUNCTION CHANGED. "
        "Existing SQL-capable functions may not gain or lose "
        "database execution calls without explicit security review:\n"
        + "\n".join(mismatches)
    )



def test_raw_sql_text_must_be_static_literal() -> None:
    """User/AI/runtime values may never construct raw SQL text."""
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

            name = _call_name(node)

            if name == "text":
                if not node.args:
                    violations.append(
                        f"{relative}:{node.lineno} "
                        "text() without SQL literal"
                    )
                    continue

                sql = node.args[0]

                if not (
                    isinstance(sql, ast.Constant)
                    and isinstance(sql.value, str)
                ):
                    violations.append(
                        f"{relative}:{node.lineno} "
                        "dynamic text() SQL"
                    )

            if name in {
                "exec_driver_sql",
                "executemany",
            }:
                if not node.args:
                    violations.append(
                        f"{relative}:{node.lineno} "
                        f"{name}() without SQL literal"
                    )
                    continue

                sql = node.args[0]

                if not (
                    isinstance(sql, ast.Constant)
                    and isinstance(sql.value, str)
                ):
                    violations.append(
                        f"{relative}:{node.lineno} "
                        f"dynamic {name}() SQL"
                    )

    assert not violations, (
        "DYNAMIC RAW SQL IS FORBIDDEN. "
        "SQL structure must be a static reviewed literal; "
        "all user, tenant, API, and AI-provided values must use "
        "bound parameters:\n"
        + "\n".join(sorted(violations))
    )



def test_execution_sql_sources_are_static_reviewed() -> None:
    """Every approved DB execution call must have static SQL provenance."""

    violations: list[str] = []

    def source_is_static(
        node: ast.AST,
        assignments: dict[str, list[ast.AST]],
        seen: set[str] | None = None,
    ) -> bool:
        seen = set() if seen is None else set(seen)

        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
        ):
            return True

        if isinstance(node, ast.Call):
            if _call_name(node) != "text":
                return False

            if len(node.args) != 1:
                return False

            sql = node.args[0]

            return (
                isinstance(sql, ast.Constant)
                and isinstance(sql.value, str)
            )

        if isinstance(node, ast.Name):
            if node.id in seen:
                return False

            sources = assignments.get(
                node.id,
                [],
            )

            if not sources:
                return False

            return all(
                source_is_static(
                    source,
                    assignments,
                    seen | {node.id},
                )
                for source in sources
            )

        # Explicitly reject f-strings, concatenation,
        # %-formatting, .format(), function-derived SQL,
        # SQLAlchemy expression construction, etc.
        return False

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(
            APP_ROOT
        ).as_posix()

        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        )

        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        ]

        for function in functions:
            assignments: dict[
                str,
                list[ast.AST],
            ] = {}

            for node in ast.walk(function):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(
                            target,
                            ast.Name,
                        ):
                            assignments.setdefault(
                                target.id,
                                [],
                            ).append(
                                node.value
                            )

                if (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(
                        node.target,
                        ast.Name,
                    )
                    and node.value is not None
                ):
                    assignments.setdefault(
                        node.target.id,
                        [],
                    ).append(
                        node.value
                    )

            for node in ast.walk(function):
                if not isinstance(
                    node,
                    ast.Call,
                ):
                    continue

                method = _call_name(node)

                if method not in EXECUTION_CALLS:
                    continue

                if not node.args:
                    violations.append(
                        f"{relative}:{node.lineno} "
                        f"{function.name}::{method} "
                        "has no reviewed SQL source"
                    )
                    continue

                if not source_is_static(
                    node.args[0],
                    assignments,
                ):
                    violations.append(
                        f"{relative}:{node.lineno} "
                        f"{function.name}::{method} "
                        "uses non-static SQL provenance"
                    )

    assert not violations, (
        "UNREVIEWED SQL SOURCE DETECTED. "
        "Database execution must originate from a "
        "static reviewed SQL literal. Runtime, user, "
        "tenant, API, or AI values may never construct "
        "SQL structure:\n"
        + "\n".join(sorted(violations))
    )



def test_sql_execution_allowlist_has_no_stale_entries() -> None:
    discovered: set[tuple[str, str]] = set()

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

            if _call_name(node) not in EXECUTION_CALLS:
                continue

            function = _enclosing_function(
                tree,
                node,
            )

            discovered.add(
                (relative, function)
            )

    stale = (
        ALLOWED_SQL_EXECUTION_POINTS
        - discovered
    )

    assert not stale, (
        "SQL boundary allowlist contains stale entries: "
        + repr(sorted(stale))
    )
