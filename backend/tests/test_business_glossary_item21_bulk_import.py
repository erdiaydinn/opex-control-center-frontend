import csv
import io
import json
from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.bulk_import import (
    GlossaryBulkImportError,
    GlossaryImportAction,
    plan_bulk_import,
    rows_from_api,
    rows_from_csv,
)
from app.platform.business_glossary.models import GlossaryScope, GlossaryStatus, GlossaryTerm, LocalizedText


def _effective() -> GlossaryTerm:
    return GlossaryTerm(
        concept_id="nsfr",
        canonical_key="nsfr",
        scope=GlossaryScope(tenant_id="tenant-a", country="TR", business_unit="Market", domain="operations"),
        status=GlossaryStatus.EFFECTIVE,
        version=1,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        display_name=LocalizedText(values={"tr": "NSFR", "en": "NSFR"}),
        short_definition=LocalizedText(values={"tr": "Net Sipariş Hata Oranı", "en": "Net Service Failure Rate"}),
        formula="PFR + Refund + Compensation",
        unit="percent",
        data_source_refs=["curated_data_shared.orders"],
        owner="semantic-governance",
    )


def _payload(formula: str = "PFR + Refund + Compensation") -> dict:
    return {
        "tenant_id": "tenant-a",
        "concept_id": "nsfr",
        "canonical_key": "nsfr",
        "country": "TR",
        "business_unit": "Market",
        "domain": "operations",
        "display_name": {"tr": "NSFR", "en": "NSFR"},
        "short_definition": {"tr": "Net Sipariş Hata Oranı", "en": "Net Service Failure Rate"},
        "formula": formula,
        "unit": "percent",
        "data_source_refs": ["curated_data_shared.orders"],
        "owner": "semantic-governance",
    }


def _csv(payload: dict) -> str:
    fields = list(payload)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    encoded = {}
    json_fields = {"display_name", "short_definition", "data_source_refs"}
    for key, value in payload.items():
        encoded[key] = json.dumps(value, ensure_ascii=False) if key in json_fields else value
    writer.writerow(encoded)
    return buf.getvalue()


def test_csv_and_api_produce_same_deterministic_review_plan() -> None:
    payload = _payload("PFR + Refund + Compensation - ApprovedExclusions")
    current = _effective()
    api_plan = plan_bulk_import(tenant_id="tenant-a", rows=rows_from_api([payload]), current_terms=[current], actor_id="owner-1")
    csv_plan = plan_bulk_import(tenant_id="tenant-a", rows=rows_from_csv(_csv(payload)), current_terms=[current], actor_id="owner-1")

    assert api_plan.fingerprint == csv_plan.fingerprint
    assert api_plan.entries == csv_plan.entries
    entry = api_plan.entries[0]
    assert entry.action is GlossaryImportAction.NEW_VERSION_DRAFT
    assert entry.source_version == 1
    assert entry.proposed_version == 2
    assert entry.proposed_term is not None
    assert entry.proposed_term.status is GlossaryStatus.DRAFT
    assert entry.proposed_term.effective_from is None
    assert [diff.field for diff in entry.diff] == ["formula"]
    assert current.version == 1
    assert current.status is GlossaryStatus.EFFECTIVE
    assert current.formula == "PFR + Refund + Compensation"
    assert api_plan.review_required is True
    assert api_plan.automatic_effective_permitted is False


def test_no_change_does_not_create_useless_version() -> None:
    plan = plan_bulk_import(tenant_id="tenant-a", rows=rows_from_api([_payload()]), current_terms=[_effective()], actor_id="owner-1")
    entry = plan.entries[0]
    assert entry.action is GlossaryImportAction.NO_CHANGE
    assert entry.source_version == 1
    assert entry.proposed_version is None
    assert entry.proposed_term is None
    assert entry.diff == []


def test_new_concept_starts_as_reviewable_draft_v1() -> None:
    payload = _payload()
    payload.update(concept_id="putaway", canonical_key="putaway", display_name={"en": "Putaway"}, short_definition={"en": "Storage after receiving"})
    plan = plan_bulk_import(tenant_id="tenant-a", rows=rows_from_api([payload]), current_terms=[_effective()], actor_id="owner-1")
    entry = plan.entries[0]
    assert entry.action is GlossaryImportAction.NEW_DRAFT
    assert entry.proposed_version == 1
    assert entry.proposed_term is not None and entry.proposed_term.status is GlossaryStatus.DRAFT


def test_duplicate_and_cross_tenant_rows_fail_closed() -> None:
    row = _payload()
    with pytest.raises(GlossaryBulkImportError, match="duplicate"):
        plan_bulk_import(tenant_id="tenant-a", rows=rows_from_api([row, row]), current_terms=[_effective()], actor_id="owner-1")
    other = dict(row, tenant_id="tenant-b")
    with pytest.raises(GlossaryBulkImportError, match="cross-tenant"):
        plan_bulk_import(tenant_id="tenant-a", rows=rows_from_api([other]), current_terms=[_effective()], actor_id="owner-1")
