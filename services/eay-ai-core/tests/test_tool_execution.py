import pytest

from app.bigquery_safe_executor import ExecutionAuditStore
from app.legal_engine import LegalEngine, LegalInstrumentUpsert, LegalRequirementUpsert
from app.tool_execution import (
    TemplateBigQueryAdapter,
    TemplateToolExecutionRequest,
    execute_with_adapter,
    prepare_execution,
)


class FakeAdapter:
    def __init__(self, *, dry_bytes=100, rows=None):
        self.dry_bytes = dry_bytes
        self.rows = rows or [{"vendor_name": "Test", "orders": 5}]
        self.last_sql = None
        self.last_parameters = None

    def dry_run(self, sql, parameters, *, timeout_ms):
        self.last_sql = sql
        self.last_parameters = parameters
        return self.dry_bytes

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        self.last_sql = sql
        self.last_parameters = parameters
        return self.rows


class FakeBQ:
    class ArrayQueryParameter:
        def __init__(self, name, type_name, value):
            self.name = name
            self.type_name = type_name
            self.value = value

    class ScalarQueryParameter:
        def __init__(self, name, type_name, value):
            self.name = name
            self.type_name = type_name
            self.value = value


def test_template_execution_rejects_missing_scope(tmp_path):
    payload = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={"query": "milk", "field": "product", "limit": 10},
        granted_scopes=[],
        reason="catalog lookup",
    )
    with pytest.raises(PermissionError, match="catalog:read"):
        prepare_execution(payload)


def test_template_execution_never_accepts_model_sql(tmp_path):
    payload = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={"query": "milk", "field": "product", "limit": 10},
        granted_scopes=["catalog:read"],
        reason="catalog lookup",
    )
    request, query_id, scopes, grounding = prepare_execution(payload)
    assert query_id == "catalog.lookup.v1"
    assert scopes == ["catalog:read"]
    assert grounding is None
    assert "pandora__vendor_products_qcomm_catalog_details" in request.sql
    assert "milk" not in request.sql
    assert request.parameters["query"] == "milk"


def test_template_execution_runs_bounded_query_and_audits(tmp_path):
    db = tmp_path / "eay.db"
    payload = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={"query": "egg", "field": "product", "limit": 10},
        granted_scopes=["catalog:read"],
        requested_by="test-user",
        reason="impact review",
        execute=True,
        max_rows=2,
        maximum_bytes_billed=1000,
    )
    adapter = FakeAdapter(rows=[{"product_name": "Egg", "email": "user@example.com"}])
    result = execute_with_adapter(payload, adapter=adapter, audit_store=ExecutionAuditStore(db))
    assert result.query_id == "catalog.lookup.v1"
    assert result.model_authored_sql_allowed is False
    assert result.execution.status == "executed"
    assert "LIMIT 2" in adapter.last_sql
    assert result.execution.rows[0]["email"] != "user@example.com"


def test_tool_semantics_fail_closed_when_template_not_implemented():
    payload = TemplateToolExecutionRequest(
        tool="ops_kpi_query",
        arguments={
            "metric": "nsfr",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "stores": [],
            "limit": 20,
        },
        granted_scopes=["ops:read"],
        reason="nsfr review",
    )
    with pytest.raises(ValueError, match="metric_template_not_implemented"):
        prepare_execution(payload)


def test_regulatory_impact_rejects_caller_authored_topic():
    payload = TemplateToolExecutionRequest(
        tool="regulatory_impact_query",
        arguments={
            "instrument_id": "tgk-1",
            "as_of": "2026-08-10",
            "topic": "caller supplied milk",
            "entities": ["sku"],
            "limit": 20,
        },
        granted_scopes=["legal:read", "catalog:read"],
        reason="impact review",
    )
    with pytest.raises(ValueError, match="extra_forbidden"):
        prepare_execution(payload)


def test_regulatory_impact_resolves_topics_from_verified_effective_instrument(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="tgk-etiket",
            title="Türk Gıda Kodeksi Etiketleme Kuralı",
            instrument_type="regulation",
            publication_date="2026-01-01",
            effective_from="2026-02-01",
            source_url="https://www.resmigazete.gov.tr/example",
            verification_status="verified",
            topics=["yumurta", "etiketleme"],
        )
    )
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="tgk-etiket-r1",
            authority="legal",
            source_id="tgk-etiket",
            scope="yumurta",
            dimension="etiketleme",
            operator="required",
            text_value="son tüketim tarihi",
            effective_from="2026-02-01",
            citation="Madde 5",
        )
    )
    payload = TemplateToolExecutionRequest(
        tool="regulatory_impact_query",
        arguments={
            "instrument_id": "tgk-etiket",
            "as_of": "2026-08-10",
            "entities": ["sku", "category"],
            "limit": 20,
        },
        granted_scopes=["legal:read", "catalog:read"],
        reason="impact review",
    )
    request, query_id, scopes, grounding = prepare_execution(payload, legal_db_path=db)
    assert query_id == "regulatory.impact.v1"
    assert scopes == ["legal:read", "catalog:read"]
    assert request.parameters["topics"][:2] == ["yumurta", "etiketleme"]
    assert grounding["instrument_id"] == "tgk-etiket"
    assert grounding["citation_ids"] == ["tgk-etiket-r1"]
    assert grounding["source_url"].startswith("https://www.resmigazete.gov.tr/")
    assert "UNNEST(@topics)" in request.sql


def test_regulatory_impact_rejects_unverified_or_not_effective_instrument(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="draft-1",
            title="Draft Food Rule",
            instrument_type="regulation",
            publication_date="2026-01-01",
            effective_from="2026-09-01",
            source_url="https://www.resmigazete.gov.tr/example",
            verification_status="draft",
            topics=["süt"],
        )
    )
    payload = TemplateToolExecutionRequest(
        tool="regulatory_impact_query",
        arguments={
            "instrument_id": "draft-1",
            "as_of": "2026-08-10",
            "entities": ["sku"],
            "limit": 20,
        },
        granted_scopes=["legal:read", "catalog:read"],
        reason="impact review",
    )
    with pytest.raises(ValueError, match="verified_effective_legal_instrument_required"):
        prepare_execution(payload, legal_db_path=db)


def test_template_bigquery_adapter_encodes_array_parameter_without_network():
    adapter = TemplateBigQueryAdapter.__new__(TemplateBigQueryAdapter)
    adapter.bigquery = FakeBQ
    params = adapter._parameters({"stores": ["Fulya", "Dicle"], "stores_empty": False})
    assert params[0].type_name == "STRING"
    assert params[0].value == ["Fulya", "Dicle"]
    assert params[1].type_name == "BOOL"
