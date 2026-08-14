from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .tool_contracts import ToolPlan
from .tool_router import validate_read_only_sql


@dataclass(frozen=True)
class QueryTemplate:
    query_id: str
    sql: str
    parameter_names: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        payload = {
            "query_id": self.query_id,
            "sql": self.sql,
            "parameter_names": list(self.parameter_names),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


TEMPLATES: dict[str, QueryTemplate] = {
    "ops.kpi.orders.v1": QueryTemplate(
        query_id="ops.kpi.orders.v1",
        sql="""
SELECT
  DATE(partition_date_local) AS date,
  vendor_name,
  COUNT(DISTINCT order_id) AS orders
FROM `curated_data_shared_coredata_business.orders`
WHERE DATE(partition_date_local) BETWEEN @start_date AND @end_date
  AND (@stores_empty OR vendor_name IN UNNEST(@stores))
GROUP BY 1,2
ORDER BY 1 DESC,3 DESC
""".strip(),
        parameter_names=("start_date", "end_date", "stores", "stores_empty"),
    ),
    "catalog.lookup.v1": QueryTemplate(
        query_id="catalog.lookup.v1",
        sql="""
SELECT *
FROM `pandata_datamart.pandora__vendor_products_qcomm_catalog_details`
WHERE LOWER(CAST(product_name AS STRING)) LIKE CONCAT('%', LOWER(@query), '%')
LIMIT @limit
""".strip(),
        parameter_names=("query", "limit"),
    ),
    "regulatory.impact.v1": QueryTemplate(
        query_id="regulatory.impact.v1",
        sql="""
SELECT
  sku,
  product_name,
  category_name,
  vendor_name
FROM `pandata_datamart.pandora__vendor_products_qcomm_catalog_details`
WHERE EXISTS (
  SELECT 1
  FROM UNNEST(@topics) AS topic
  WHERE LOWER(CONCAT(COALESCE(product_name,''),' ',COALESCE(category_name,'')))
    LIKE CONCAT('%', LOWER(topic), '%')
)
LIMIT @limit
""".strip(),
        parameter_names=("topics", "limit"),
    ),
}


def compile_tool_plan(plan: ToolPlan) -> tuple[str, dict[str, Any]]:
    if plan.model_authored_sql_allowed:
        raise ValueError("model_authored_sql_must_remain_disabled")
    template = TEMPLATES.get(plan.query_id)
    if template is None:
        raise ValueError("unknown_query_template")
    validate_read_only_sql(template.sql)
    args = plan.arguments
    if plan.query_id == "ops.kpi.orders.v1":
        if args["metric"] != "orders":
            raise ValueError(f"metric_template_mismatch:{args['metric']}:{plan.query_id}")
        params = {
            "start_date": args["start_date"],
            "end_date": args["end_date"],
            "stores": args.get("stores", []),
            "stores_empty": not bool(args.get("stores")),
        }
    elif plan.query_id == "catalog.lookup.v1":
        if args["field"] != "product":
            raise ValueError(f"catalog_field_template_not_implemented:{args['field']}")
        params = {"query": args["query"], "limit": args["limit"]}
    elif plan.query_id == "regulatory.impact.v1":
        topics = args.get("verified_topics") or []
        if not isinstance(topics, list) or not topics:
            raise ValueError("verified_legal_impact_topics_required")
        if any(not isinstance(topic, str) or not topic.strip() for topic in topics):
            raise ValueError("invalid_verified_legal_impact_topics")
        unsupported_entities = set(args.get("entities", [])) - {"sku", "category", "supplier"}
        if unsupported_entities:
            raise ValueError(
                "impact_entity_template_not_implemented:" + ",".join(sorted(unsupported_entities))
            )
        params = {"topics": topics, "limit": args["limit"]}
    else:
        raise ValueError("unsupported_query_template")
    missing = set(template.parameter_names) - set(params)
    if missing:
        raise ValueError(f"missing_template_parameters:{','.join(sorted(missing))}")
    return template.sql, params
