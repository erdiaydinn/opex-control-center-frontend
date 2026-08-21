from app.shared_platform.contracts import IntegrationContract, SearchDocument
from app.shared_platform.search_integration import (
    SearchPrincipal,
    validate_inbound_payload,
    visible_search_documents,
)


def test_operational_search_requires_permission_and_provenance() -> None:
    documents = (
        SearchDocument(
            source_module="inventory",
            source_type="sku",
            source_id="1",
            title="Milk",
            search_text="milk",
            permission_key="module:inventory:view",
            provenance={"source": "inventory"},
        ),
        SearchDocument(
            source_module="budget",
            source_type="line",
            source_id="2",
            title="Budget",
            search_text="budget",
            permission_key="module:budget:view",
            provenance={"source": "budget"},
        ),
        SearchDocument(
            source_module="inventory",
            source_type="sku",
            source_id="3",
            title="Unknown source",
            search_text="unknown",
            permission_key="module:inventory:view",
            provenance={},
        ),
    )
    principal = SearchPrincipal(frozenset({"module:inventory:view"}))
    visible = visible_search_documents(principal, documents)
    assert [document.source_id for document in visible] == ["1"]


def test_integration_import_rejects_payload_tenant_and_schema_drift() -> None:
    contract = IntegrationContract(
        connector_key="hr-roster",
        direction="INBOUND",
        version=1,
        schema={},
        validation_policy={
            "required_fields": ["employee_id"],
            "allowed_fields": ["employee_id", "name"],
        },
    )
    assert validate_inbound_payload(
        contract,
        {"employee_id": "E1", "name": "Ada"},
    ) == (True, ())

    ok, errors = validate_inbound_payload(
        contract,
        {"employee_id": "E1", "tenant_id": "evil"},
    )
    assert not ok
    assert "tenant_id:payload_authority_forbidden" in errors
    assert "tenant_id:unexpected" in errors

    ok, errors = validate_inbound_payload(contract, {"name": "Ada"})
    assert not ok
    assert "employee_id:required" in errors
