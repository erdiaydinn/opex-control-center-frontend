from app.entrypoint import app


def _paths() -> set[str]:
    return set(app.openapi().get("paths", {}))


def test_governed_tool_execution_is_public_but_raw_bigquery_executor_is_not():
    paths = _paths()
    assert "/v1/tool-execution" in paths
    assert "/v1/bigquery/execute" not in paths
    assert "/v1/bigquery/dry-run" not in paths


def test_raw_sql_validation_route_does_not_restore_execution_bypass():
    paths = _paths()
    assert "/v1/tools/execute" not in paths
