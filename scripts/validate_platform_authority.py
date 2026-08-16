#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MANIFEST_PATH = Path("config/eay_platform_authority_contract.json")
CORE_MODULE_ROOT = Path("services/core-api/app/modules")
LOCALIZATION_PATH = Path("services/core-api/app/core/localization.py")
FIELD_AUTHORIZATION_PATH = Path(
    "services/core-api/app/modules/field_intelligence/authorization.py"
)
FIELD_SCHEMAS_PATH = Path("services/core-api/app/modules/field_intelligence/schemas.py")

RAW_SCOPE_PATTERN = re.compile(r"\bprincipal\.permission_assignments\b")
LOCAL_LOCALE_PATTERN = re.compile(
    r"^\s*(SUPPORTED_LOCALES|SUPPORTED_LOCALE_SET|RTL_LOCALES)\s*=",
    re.MULTILINE,
)
TENANT_HEADER_PATTERN = re.compile(
    r"(?:headers?\s*\.\s*(?:get|getlist)\s*\([^\n)]*x[-_]tenant|"
    r"Header\s*\([^\n)]*tenant)",
    re.IGNORECASE,
)
TENANT_QUERY_PATTERN = re.compile(
    r"\btenant(?:_id)?\s*:\s*[^\n=]+?=\s*Query\s*\(",
    re.IGNORECASE,
)
AUDIT_SINK_PATTERN = re.compile(
    r"(?:CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?audit_events|"
    r"INSERT\s+INTO\s+audit_events)",
    re.IGNORECASE,
)


def _canonical_file(value: str) -> Path:
    return Path(value.split(":", 1)[0])


def _python_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.rglob("*.py") if item.is_file())


def scan_module_source(
    relative: Path,
    text: str,
    forbidden_imports: tuple[str, ...],
) -> list[str]:
    violations: list[str] = []

    if RAW_SCOPE_PATTERN.search(text):
        violations.append(f"{relative}: raw permission assignments are Core authority only")
    if LOCAL_LOCALE_PATTERN.search(text):
        violations.append(f"{relative}: competing locale matrix is forbidden")
    if TENANT_HEADER_PATTERN.search(text):
        violations.append(f"{relative}: tenant authority cannot come from request headers")
    if TENANT_QUERY_PATTERN.search(text):
        violations.append(f"{relative}: tenant authority cannot come from query parameters")
    if AUDIT_SINK_PATTERN.search(text):
        violations.append(f"{relative}: competing platform audit sink is forbidden")

    lowered = text.casefold()
    for dependency in forbidden_imports:
        normalized = dependency.casefold()
        if f"import {normalized}" in lowered or f"from {normalized}" in lowered:
            violations.append(
                f"{relative}: direct notification transport {dependency} is forbidden"
            )

    return violations


def validate(root: Path) -> list[str]:
    root = root.resolve()
    manifest_file = root / MANIFEST_PATH
    if not manifest_file.is_file():
        return [f"missing authority manifest: {MANIFEST_PATH}"]

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    violations: list[str] = []

    if manifest.get("production_ready") is not False:
        violations.append("authority repository contract must not claim production readiness")

    principles = manifest.get("principles")
    if not isinstance(principles, dict) or not principles or not all(
        value is True for value in principles.values()
    ):
        violations.append("all platform authority principles must be explicit true invariants")

    truth = manifest.get("truth_boundary", {})
    if truth.get("repository_contract_is_production_identity_evidence") is not False:
        violations.append("repository authority contract cannot be production identity evidence")
    if truth.get("production_activation_permitted") is not False:
        violations.append("authority contract cannot permit production activation")

    authorities = manifest.get("authorities", {})
    required_authorities = {
        "authenticated_identity",
        "tenant_membership_roles_permissions",
        "permission_scope",
        "locale",
        "notification_transport",
        "audit",
    }
    missing = required_authorities - set(authorities)
    if missing:
        violations.append(f"missing canonical authorities: {', '.join(sorted(missing))}")

    for name, authority in authorities.items():
        if not isinstance(authority, dict):
            violations.append(f"authority {name} must be an object")
            continue
        references: list[str] = []
        canonical = authority.get("canonical")
        entrypoints = authority.get("entrypoints")
        database_resolution = authority.get("database_resolution")
        if isinstance(canonical, str):
            references.append(canonical)
        elif isinstance(canonical, list):
            references.extend(str(item) for item in canonical)
        if isinstance(entrypoints, list):
            references.extend(str(item) for item in entrypoints)
        if isinstance(database_resolution, str):
            references.append(database_resolution)

        for reference in references:
            path = root / _canonical_file(reference)
            if not path.exists():
                violations.append(f"authority {name} references missing path: {reference}")

    locale_authority = authorities.get("locale", {})
    supported = locale_authority.get("supported", [])
    if supported != ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"]:
        violations.append("locale authority must preserve the canonical 10-language order")
    if locale_authority.get("rtl") != ["ar"]:
        violations.append("Arabic must remain the canonical RTL locale")

    localization_text = (root / LOCALIZATION_PATH).read_text(encoding="utf-8")
    for locale in supported:
        if f'"{locale}"' not in localization_text:
            violations.append(f"locale authority source is missing {locale}")

    field_authorization = (root / FIELD_AUTHORIZATION_PATH).read_text(encoding="utf-8")
    if "resolve_permission_scope" not in field_authorization:
        violations.append("Field Intelligence must consume Core permission scope authority")
    if "permission_assignments" in field_authorization:
        violations.append("Field Intelligence must not inspect raw permission assignments")

    field_schemas = (root / FIELD_SCHEMAS_PATH).read_text(encoding="utf-8")
    if "from app.core.localization import SUPPORTED_LOCALE_SET" not in field_schemas:
        violations.append("Field Intelligence must consume Core locale authority")

    forbidden_imports = tuple(
        str(value).strip()
        for value in manifest.get("module_transport_forbidden_imports", [])
        if str(value).strip()
    )

    for path in _python_files(root / CORE_MODULE_ROOT):
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        violations.extend(scan_module_source(relative, text, forbidden_imports))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    violations = validate(args.root)
    if violations:
        print("EAY Platform Core authority boundary: FAIL")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("EAY Platform Core authority boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
