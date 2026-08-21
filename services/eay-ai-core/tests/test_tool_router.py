import pytest

from app.tool_router import bounded_sql, validate_read_only_sql


def test_allows_read_only_allowlisted_query():
    sql = "SELECT * FROM `curated_data_shared.orders` WHERE entity.id = 'YS_TR'"
    validate_read_only_sql(sql)
    assert bounded_sql(sql, 200).endswith("LIMIT 200")


def test_rejects_mutation():
    with pytest.raises(ValueError, match="mutating_or_privileged_sql_not_allowed"):
        validate_read_only_sql("DELETE FROM `curated_data_shared.orders` WHERE TRUE")


def test_rejects_multiple_statements():
    with pytest.raises(ValueError, match="multiple_statements_not_allowed"):
        validate_read_only_sql(
            "SELECT * FROM `curated_data_shared.orders`; SELECT 1"
        )


def test_rejects_non_allowlisted_dataset():
    with pytest.raises(ValueError, match="dataset_not_allowlisted"):
        validate_read_only_sql("SELECT * FROM `other_project.secret.payroll`")


def test_allows_cte():
    validate_read_only_sql(
        "WITH x AS (SELECT 1 AS id) SELECT * FROM x"
    )
