from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_platform_authority.py"
SPEC = spec_from_file_location("validate_platform_authority", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _scan(source: str) -> list[str]:
    return MODULE.scan_module_source(
        Path("services/core-api/app/modules/example/router.py"),
        source,
        ("smtplib", "sendgrid", "firebase_admin.messaging"),
    )


def test_rejects_raw_permission_assignment_reconstruction():
    violations = _scan("items = principal.permission_assignments\n")
    assert any("raw permission assignments" in item for item in violations)


def test_rejects_tenant_header_authority():
    violations = _scan('tenant = request.headers.get("X-Tenant-ID")\n')
    assert any("request headers" in item for item in violations)


def test_rejects_tenant_query_authority():
    violations = _scan("tenant_id: str = Query(...)\n")
    assert any("query parameters" in item for item in violations)


def test_rejects_competing_locale_matrix():
    violations = _scan('SUPPORTED_LOCALES = {"tr", "en"}\n')
    assert any("competing locale matrix" in item for item in violations)


def test_rejects_module_owned_notification_transport():
    violations = _scan("import smtplib\n")
    assert any("direct notification transport" in item for item in violations)


def test_rejects_competing_platform_audit_sink():
    violations = _scan('sql = "INSERT INTO audit_events (tenant_id) VALUES (:tenant)"\n')
    assert any("competing platform audit sink" in item for item in violations)


def test_current_repository_authority_contract_is_clean():
    assert MODULE.validate(REPO_ROOT) == []
