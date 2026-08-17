"""Secret-free payload schema inference for Jarvis API auto-discovery.

Observed payload values are transient inputs to these pure functions. Returned
objects retain only structural type information, field paths and fingerprints;
they never retain the actual business values, tokens, passwords, cookies or
GraphQL query text.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

API_SCHEMA_CONTRACT = "eay-api-schema-intelligence-v1"

_SENSITIVE_FIELD_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "jwt",
    "password",
    "passwd",
    "refresh_token",
    "secret",
    "set-cookie",
    "token",
}
_GRAPHQL_OPERATION = re.compile(
    r"\b(query|mutation|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)?",
    re.IGNORECASE,
)


class ApiProtocol(str, Enum):
    JSON_HTTP = "json_http"
    GRAPHQL = "graphql"
    UNKNOWN = "unknown"


class GraphQLOperationKind(str, Enum):
    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"
    UNKNOWN = "unknown"


class PayloadSchemaObservation(BaseModel):
    contract: str = API_SCHEMA_CONTRACT
    protocol: ApiProtocol
    schema: dict[str, Any]
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_paths: tuple[str, ...] = ()
    sensitive_field_paths: tuple[str, ...] = ()
    graphql_operation_kind: GraphQLOperationKind = GraphQLOperationKind.UNKNOWN
    graphql_operation_name: str | None = None
    raw_values_retained: bool = False
    raw_query_retained: bool = False


def _scalar_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "unknown"


def _shape(value: Any, *, path: str, fields: list[str], sensitive: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        properties: dict[str, Any] = {}
        for key in sorted(str(item) for item in value.keys()):
            child_path = f"{path}.{key}" if path else key
            fields.append(child_path)
            if key.casefold() in _SENSITIVE_FIELD_NAMES:
                sensitive.append(child_path)
            properties[key] = _shape(value[key], path=child_path, fields=fields, sensitive=sensitive)
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
        }
    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {"type": "unknown"}}
        item_shapes = [_shape(item, path=f"{path}[]", fields=fields, sensitive=sensitive) for item in value[:20]]
        canonical_items = {
            json.dumps(item, sort_keys=True, separators=(",", ":")): item for item in item_shapes
        }
        if len(canonical_items) == 1:
            items = next(iter(canonical_items.values()))
        else:
            items = {"oneOf": [canonical_items[key] for key in sorted(canonical_items)]}
        return {"type": "array", "items": items}
    return {"type": _scalar_type(value)}


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _graphql_metadata(payload: Any) -> tuple[ApiProtocol, GraphQLOperationKind, str | None, Any]:
    if not isinstance(payload, dict) or "query" not in payload:
        return ApiProtocol.JSON_HTTP, GraphQLOperationKind.UNKNOWN, None, payload

    query_text = payload.get("query")
    operation_name = payload.get("operationName") if isinstance(payload.get("operationName"), str) else None
    operation_kind = GraphQLOperationKind.UNKNOWN
    if isinstance(query_text, str):
        match = _GRAPHQL_OPERATION.search(query_text)
        if match:
            operation_kind = GraphQLOperationKind(match.group(1).casefold())
            if not operation_name and match.group(2):
                operation_name = match.group(2)

    # Never carry the GraphQL document itself into the retained schema. Its
    # structure is represented by the operation metadata and variable shape.
    retained_payload = {
        "operationName": operation_name,
        "variables": payload.get("variables", {}),
    }
    return ApiProtocol.GRAPHQL, operation_kind, operation_name, retained_payload


def infer_payload_schema(payload: Any) -> PayloadSchemaObservation:
    protocol, graphql_kind, graphql_name, retained = _graphql_metadata(payload)
    fields: list[str] = []
    sensitive: list[str] = []
    schema = _shape(retained, path="", fields=fields, sensitive=sensitive)
    return PayloadSchemaObservation(
        protocol=protocol,
        schema=schema,
        schema_fingerprint=_fingerprint(schema),
        field_paths=tuple(sorted(set(fields))),
        sensitive_field_paths=tuple(sorted(set(sensitive))),
        graphql_operation_kind=graphql_kind,
        graphql_operation_name=graphql_name,
    )


def schemas_compatible(left: PayloadSchemaObservation, right: PayloadSchemaObservation) -> bool:
    """Strict structural compatibility for learned capability revisions.

    The first production promotion should prefer strictness. More permissive
    backwards-compatible evolution can later be delegated to a dedicated
    OpenAPI diff policy, but silent schema drift must never be accepted here.
    """
    return left.protocol is right.protocol and left.schema_fingerprint == right.schema_fingerprint
