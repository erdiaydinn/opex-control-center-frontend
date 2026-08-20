import sqlite3

import pytest
from pydantic import SecretStr, ValidationError

from app.bigquery_safe_executor import ExecutionAuditStore
from app.legal_engine import (
    LegalEngine,
    LegalInstrumentUpsert,
    LegalRequirementUpsert,
)
from app.platform_tool_authorizer import (
    TrustedToolExecutionContext,
    tool_arguments_sha256,
    tool_reason_sha256,
)
from app.tool_contracts import build_tool_plan
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

    def execute(
        self,
        sql,
        parameters,
        *,
        timeout_ms,
        maximum_bytes_billed,
    ):
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


def payload_for(
    *,
    tool="catalog_query",
    arguments=None,
    reason="catalog lookup",
    execute=False,
    **updates,
):
    payload = TemplateToolExecutionRequest(
        tool=tool,
        arguments=arguments
        or {"query": "milk", "field": "product", "limit": 10},
        grant_token="g" * 43,
        reason=reason,
        execute=execute,
    )
    return payload.model_copy(update=updates)


def _trusted_context_base(
    *,
    tool: str,
    scopes: tuple[str, ...],
    arguments_sha256: str,
    reason_sha256: str,
    actor: str = "platform:user-1",
) -> TrustedToolExecutionContext:
    return TrustedToolExecutionContext(
        request_id="platform-auth-1",
        tenant_id="11111111-1111-4111-8111-111111111111",
        actor_subject=actor,
        tool=tool,
        granted_scopes=scopes,
        data_scope={"store_names": []},
        data_scope_fingerprint="d" * 64,
        tenant_entity_ids=("YS_TR",),
        tenant_query_context_fingerprint="b" * 64,
        query_contract_id="test.contract.v1",
        query_contract_revision=1,
        query_contract_fingerprint="c" * 64,
        execution_scope_fingerprint="e" * 64,
        authorization_fingerprint="a" * 64,
        arguments_sha256=arguments_sha256,
        reason_sha256=reason_sha256,
        admission_lease_token=SecretStr("l" * 43),
        admission_lease_ttl_seconds=135,
    )


def trusted_context(
    payload: TemplateToolExecutionRequest,
    *,
    actor="platform:user-1",
):
    plan = build_tool_plan(payload.tool, payload.arguments)
    return _trusted_context_base(
        tool=plan.tool,
        scopes=tuple(plan.required_scope),
        arguments_sha256=tool_arguments_sha256(plan.arguments),
        reason_sha256=tool_reason_sha256(payload.reason),
        actor=actor,
    )


def test_template_execution_request_rejects_caller_authority_fields():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TemplateToolExecutionRequest(
            tool="catalog_query",
            arguments={
                "query": "milk",
                "field": "product",
                "limit": 10,
            },
            grant_token="g" * 43,
            reason="catalog lookup",
            granted_scopes=["catalog:read"],
            requested_by="caller:user-1",
            tenant_id="11111111-1111-4111-8111-111111111111",
        )


def test_template_execution_requires_opaque_platform_grant():
    with pytest.raises(ValidationError):
        TemplateToolExecutionRequest(
            tool="catalog_query",
            arguments={
                "query": "milk",
                "field": "product",
                "limit": 10,
            },
            grant_token="too-short",
            reason="catalog lookup",
        )


def test_template_execution_rejects_forged_trusted_context():
    payload = payload_for()
    context = trusted_context(payload).model_copy(
        update={"granted_scopes": ("catalog:read", "legal:read")}
    )

    with pytest.raises(
        RuntimeError,
        match="unexpected scopes",
    ):
        prepare_execution(
            payload,
            authorization_context=context,
        )


def test_template_execution_never_accepts_model_sql():
    payload = payload_for()
    request, query_id, scopes, grounding = prepare_execution(
        payload,
        authorization_context=trusted_context(payload),
    )
    assert query_id == "catalog.lookup.v1"
    assert scopes == ["catalog:read"]
    assert grounding is None
    assert "pandora__vendor_products_qcomm_catalog_details" in request.sql
    assert "milk" not in request.sql
    assert request.parameters["query"] == "milk"
    assert request.requested_by == "platform:user-1"
    assert request.tenant_id == "11111111-1111-4111-8111-111111111111"
    assert request.authorization_request_id == "platform-auth-1"


def test_template_execution_runs_bounded_query_and_audits_platform_identity(
    tmp_path,
):
    db = tmp_path / "eay.db"
    payload = payload_for(
        arguments={
            "query": "egg",
            "field": "product",
            "limit": 10,
        },
        reason="impact review",
        execute=True,
        max_rows=2,
        maximum_bytes_billed=1000,
    )
    adapter = FakeAdapter(
        rows=[
            {
                "product_name": "Egg",
                "email": "user@example.com",
            }
        ]
    )
    context = trusted_context(payload, actor="platform:voice-user")
    result = execute_with_adapter(
        payload,
        authorization_context=context,
        adapter=adapter,
        audit_store=ExecutionAuditStore(db),
    )
    assert result.query_id == "catalog.lookup.v1"
    assert result.model_authored_sql_allowed is False
    assert result.execution.status == "executed"
    assert "LIMIT 2" in adapter.last_sql
    assert result.execution.rows[0]["email"] != "user@example.com"

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """
            SELECT requested_by, tenant_id, authorization_request_id,
                   authorization_fingerprint
            FROM bigquery_execution_audit
            WHERE id = ?
            """,
            (result.execution.execution_id,),
        ).fetchone()

    assert row == (
        "platform:voice-user",
        "11111111-1111-4111-8111-111111111111",
        "platform-auth-1",
        "a" * 64,
    )


def test_tool_semantics_fail_closed_when_template_not_implemented():
    payload = payload_for(
        tool="ops_kpi_query",
        arguments={
            "metric": "nsfr",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "stores": [],
            "limit": 20,
        },
        reason="nsfr review",
    )
    placeholder = _trusted_context_base(
        tool="ops_kpi_query",
        scopes=("ops:read",),
        arguments_sha256="b" * 64,
        reason_sha256="c" * 64,
    )
    with pytest.raises(
        ValueError,
        match="metric_template_not_implemented",
    ):
        prepare_execution(
            payload,
            authorization_context=placeholder,
        )


def test_regulatory_impact_rejects_caller_authored_topic():
    payload = payload_for(
        tool="regulatory_impact_query",
        arguments={
            "instrument_id": "tgk-1",
            "as_of": "2026-08-10",
            "topic": "caller supplied milk",
            "entities": ["sku"],
            "limit": 20,
        },
        reason="impact review",
    )
    placeholder = _trusted_context_base(
        tool="regulatory_impact_query",
        scopes=("catalog:read", "legal:read"),
        arguments_sha256="b" * 64,
        reason_sha256="c" * 64,
    )
    with pytest.raises(ValueError, match="extra_forbidden"):
        prepare_execution(
            payload,
            authorization_context=placeholder,
        )


def test_regulatory_impact_resolves_topics_from_verified_effective_instrument(
    tmp_path,
):
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
    payload = payload_for(
        tool="regulatory_impact_query",
        arguments={
            "instrument_id": "tgk-etiket",
            "as_of": "2026-08-10",
            "entities": ["sku", "category"],
            "limit": 20,
        },
        reason="impact review",
    )
    request, query_id, scopes, grounding = prepare_execution(
        payload,
        authorization_context=trusted_context(payload),
        legal_db_path=db,
    )
    assert query_id == "regulatory.impact.v1"
    assert scopes == ["legal:read", "catalog:read"]
    assert request.parameters["topics"][:2] == [
        "yumurta",
        "etiketleme",
    ]
    assert grounding["instrument_id"] == "tgk-etiket"
    assert grounding["citation_ids"] == ["tgk-etiket-r1"]
    assert grounding["source_url"].startswith(
        "https://www.resmigazete.gov.tr/"
    )
    assert "UNNEST(@topics)" in request.sql


def test_regulatory_impact_rejects_unverified_or_not_effective_instrument(
    tmp_path,
):
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
    payload = payload_for(
        tool="regulatory_impact_query",
        arguments={
            "instrument_id": "draft-1",
            "as_of": "2026-08-10",
            "entities": ["sku"],
            "limit": 20,
        },
        reason="impact review",
    )
    with pytest.raises(
        ValueError,
        match="verified_effective_legal_instrument_required",
    ):
        prepare_execution(
            payload,
            authorization_context=trusted_context(payload),
            legal_db_path=db,
        )


def test_template_bigquery_adapter_encodes_array_parameter_without_network():
    adapter = TemplateBigQueryAdapter.__new__(TemplateBigQueryAdapter)
    adapter.bigquery = FakeBQ
    params = adapter._parameters(
        {
            "stores": ["Fulya", "Dicle"],
            "stores_empty": False,
        }
    )
    assert params[0].type_name == "STRING"
    assert params[0].value == ["Fulya", "Dicle"]
    assert params[1].type_name == "BOOL"
