from app.api_schema_intelligence import (
    ApiProtocol,
    GraphQLOperationKind,
    infer_payload_schema,
    schemas_compatible,
)


def test_json_schema_inference_retains_structure_not_values():
    observation = infer_payload_schema(
        {
            "warehouseId": "fulya",
            "barcode": "8691234567890",
            "quantity": 3,
            "reason": "ZAYI",
            "token": "do-not-retain-me",
        }
    )

    serialized = observation.model_dump_json()
    assert observation.protocol is ApiProtocol.JSON_HTTP
    assert "warehouseId" in observation.field_paths
    assert "token" in observation.sensitive_field_paths
    assert "fulya" not in serialized
    assert "8691234567890" not in serialized
    assert "ZAYI" not in serialized
    assert "do-not-retain-me" not in serialized
    assert observation.raw_values_retained is False


def test_graphql_mutation_keeps_operation_metadata_but_not_query_document_or_values():
    observation = infer_payload_schema(
        {
            "operationName": "AdjustInventory",
            "query": "mutation AdjustInventory($warehouse: ID!, $qty: Int!) { adjustInventory(warehouse: $warehouse, qty: $qty) { id } }",
            "variables": {
                "warehouse": "fulya",
                "qty": 3,
                "access_token": "never-store-this",
            },
        }
    )

    serialized = observation.model_dump_json()
    assert observation.protocol is ApiProtocol.GRAPHQL
    assert observation.graphql_operation_kind is GraphQLOperationKind.MUTATION
    assert observation.graphql_operation_name == "AdjustInventory"
    assert "variables.warehouse" in observation.field_paths
    assert "variables.access_token" in observation.sensitive_field_paths
    assert "adjustInventory(" not in serialized
    assert "fulya" not in serialized
    assert "never-store-this" not in serialized
    assert observation.raw_query_retained is False


def test_graphql_operation_name_can_be_derived_from_document_without_retaining_document():
    observation = infer_payload_schema(
        {
            "query": "query ReadStock($barcode: String!) { stock(barcode: $barcode) { available } }",
            "variables": {"barcode": "8690000000000"},
        }
    )

    assert observation.graphql_operation_kind is GraphQLOperationKind.QUERY
    assert observation.graphql_operation_name == "ReadStock"
    assert "8690000000000" not in observation.model_dump_json()


def test_structural_drift_is_detected_strictly():
    v1 = infer_payload_schema({"barcode": "a", "quantity": 1})
    same_shape = infer_payload_schema({"barcode": "b", "quantity": 9})
    drifted = infer_payload_schema({"barcode": "b", "quantity": "9"})

    assert schemas_compatible(v1, same_shape) is True
    assert schemas_compatible(v1, drifted) is False
