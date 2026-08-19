from app.entrypoint import app
from app.tool_execution import TemplateToolExecutionRequest


def _paths() -> set[str]:
    return set(app.openapi().get("paths", {}))


def test_governed_tool_execution_is_public_but_raw_bigquery_executor_is_not():
    paths = _paths()
    assert "/v1/tool-execution" in paths
    assert "/v1/bigquery/execute" not in paths
    assert "/v1/bigquery/dry-run" not in paths


def test_public_tool_execution_accepts_opaque_grant_not_authority_fields():
    fields = set(TemplateToolExecutionRequest.model_fields)

    assert "grant_token" in fields
    assert "granted_scopes" not in fields
    assert "requested_by" not in fields
    assert "tenant_id" not in fields
    assert "actor_subject" not in fields
    assert "permissions" not in fields


def test_raw_sql_validation_route_does_not_restore_execution_bypass():
    paths = _paths()
    assert "/v1/tools/execute" not in paths
