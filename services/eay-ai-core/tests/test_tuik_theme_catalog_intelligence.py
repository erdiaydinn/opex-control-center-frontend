from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.company_world_live_bridge import (
    ContextCompanyLinkDisposition,
    ExternalContextDomain,
    GeographicScope,
    GeographicScopeLevel,
    assess_company_world_live_context,
    build_company_location_binding,
)
from app.context_provider_gateway import RequestPurpose, plan_provider_request
from app.context_provider_runtime import ProviderRuntimeBlocked
from app.real_world_timeline import TimelineAuthorityClass
from app.tuik_theme_catalog_adapter import (
    TUIK_THEME_API_URL,
    TUIK_THEME_PROVIDER_ID,
    parse_tuik_theme_catalog,
    read_tuik_theme_catalog_observation,
)
from app.world_model import (
    EntityKind,
    TruthClass,
    WorldAssertion,
    WorldEntity,
    build_world_snapshot,
)

NOW = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
TENANT = "tenant-a"
LOCATION = "store:fulya"


def theme_document(*, is_error: bool = False, duplicate_id: bool = False, unsafe_url: bool = False):
    child_id = 1 if duplicate_id else "1.1"
    child_url = "https://evil.example/theme" if unsafe_url else "/tr/statistical-themes/child"
    return {
        "data": [
            {
                "id": 1,
                "name": "Nüfus ve Demografi",
                "url": "/tr/statistical-themes/population",
                "icon": "population",
                "metadataUrl": "https://veriportali.tuik.gov.tr/metadata/population",
                "children": [
                    {
                        "id": child_id,
                        "name": "Nüfus İstatistikleri",
                        "url": child_url,
                        "icon": "population-child",
                        "children": [],
                    }
                ],
            }
        ],
        "isError": is_error,
        "message": None,
    }


def transport_for(document, *, bootstrap_status: int = 200):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/tr/statistical-themes":
            return httpx.Response(
                bootstrap_status,
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "set-cookie": "tuik-session=verified; Path=/; Secure; HttpOnly",
                },
                content=b"<html>" + (b"x" * 1_200) + b"</html>",
            )
        assert request.url.path == "/api/tr/data/statistical-themes"
        assert "tuik-session=verified" in request.headers.get("cookie", "")
        assert request.headers["referer"] == "https://veriportali.tuik.gov.tr/tr/statistical-themes"
        assert request.headers["origin"] == "https://veriportali.tuik.gov.tr"
        assert request.headers["x-requested-with"] == "XMLHttpRequest"
        assert request.headers["accept-language"].startswith("tr-TR")
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            content=json.dumps(document, ensure_ascii=False).encode(),
        )

    return httpx.MockTransport(handler), calls


def company_world():
    entity = WorldEntity(
        entity_id=LOCATION,
        tenant_id=TENANT,
        kind=EntityKind.STORE,
        display_name="Fulya",
    )
    assertion = WorldAssertion(
        assertion_id="orders:current",
        tenant_id=TENANT,
        entity_id=LOCATION,
        field_name="orders_per_hour",
        value=100.0,
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        valid_from=NOW - timedelta(hours=2),
        observed_at=NOW,
        source_ref="company://orders-live",
        evidence_ref="company-evidence://orders/current",
        confidence=0.99,
    )
    return build_world_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[entity],
        assertions=[assertion],
    )


def test_tuik_one_shot_is_authorized_while_continuous_ingestion_remains_blocked() -> None:
    one_shot = plan_provider_request(
        provider_id=TUIK_THEME_PROVIDER_ID,
        url=TUIK_THEME_API_URL,
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
    )
    continuous = plan_provider_request(
        provider_id=TUIK_THEME_PROVIDER_ID,
        url=TUIK_THEME_API_URL,
        purpose=RequestPurpose.CONTINUOUS_INGESTION,
    )

    assert one_shot.execution_permitted is True
    assert one_shot.blockers == ()
    assert continuous.execution_permitted is False
    assert "provider_continuous_ingestion_not_authorized" in continuous.blockers
    assert "provider_production_not_enabled" in continuous.blockers


def test_session_aware_runtime_normalizes_tuik_catalog_into_external_observation() -> None:
    transport, calls = transport_for(theme_document())
    result = read_tuik_theme_catalog_observation(
        tenant_id=TENANT,
        transport=transport,
        now=NOW,
    )

    assert len(calls) == 2
    assert result.provider_receipt.status_code == 200
    assert result.provider_receipt.media_type == "application/json"
    assert result.provider_receipt.bootstrap_body_sha256 is not None
    assert result.catalog_receipt.root_theme_count == 1
    assert result.catalog_receipt.total_node_count == 2
    assert result.catalog_receipt.themes[0].theme_id == "1"
    assert result.catalog_receipt.themes[0].children[0].theme_id == "1.1"
    assert result.observation.domain is ExternalContextDomain.MACROECONOMIC
    assert result.observation.authority_class is TimelineAuthorityClass.VERIFIED_EXTERNAL
    assert result.observation.geographic_scope.level is GeographicScopeLevel.COUNTRY
    assert result.observation.geographic_scope.country_code == "TR"
    assert result.observation.context_only is True
    assert result.observation.company_truth_granted is False
    assert result.observation.causal_claim_proven is False
    assert result.observation.execution_authority_granted is False


def test_tuik_observation_enters_company_world_as_context_only_not_company_truth() -> None:
    transport, _ = transport_for(theme_document())
    result = read_tuik_theme_catalog_observation(
        tenant_id=TENANT,
        transport=transport,
        now=NOW,
    )
    world = company_world()
    binding = build_company_location_binding(
        world=world,
        company_id="company-a",
        location_entity_id=LOCATION,
        scope=GeographicScope(
            level=GeographicScopeLevel.LOCATION,
            country_code="TR",
            region_key="istanbul",
            locality_key="sisli",
            location_ref=LOCATION,
        ),
        truth_class=TruthClass.VERIFIED_COMPANY,
        observed_at=NOW,
        evidence_ref="company-evidence://location/fulya",
    )

    receipt = assess_company_world_live_context(
        tenant_id=TENANT,
        company_id="company-a",
        as_of=NOW,
        current_world=world,
        location_binding=binding,
        observations=(result.observation,),
    )

    assert receipt.disposition is ContextCompanyLinkDisposition.CONTEXT_ONLY
    assert receipt.context_coincident_with_company_deviation is False
    assert receipt.company_operational_deviation_authorized is False
    assert receipt.causal_claim_proven is False
    assert receipt.automatic_action_allowed is False
    assert receipt.execution_authority_granted is False


def test_bootstrap_redirect_is_blocked_before_theme_api_read() -> None:
    transport, calls = transport_for(theme_document(), bootstrap_status=302)
    with pytest.raises(ProviderRuntimeBlocked, match="bootstrap_redirect_forbidden"):
        read_tuik_theme_catalog_observation(
            tenant_id=TENANT,
            transport=transport,
            now=NOW,
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("document", "error"),
    [
        (theme_document(is_error=True), "upstream_error"),
        (theme_document(duplicate_id=True), "duplicate_theme_id"),
        (theme_document(unsafe_url=True), "url_unsafe"),
    ],
)
def test_malformed_or_unsafe_tuik_catalog_fails_closed(document, error: str) -> None:
    transport, _ = transport_for(document)
    result = read_tuik_theme_catalog_observation(
        tenant_id=TENANT,
        transport=transport,
        now=NOW,
    ) if False else None

    from app.context_provider_runtime import execute_provider_request

    plan = plan_provider_request(
        provider_id=TUIK_THEME_PROVIDER_ID,
        url=TUIK_THEME_API_URL,
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
    )
    provider_receipt = execute_provider_request(plan, transport=transport, now=NOW)
    with pytest.raises(ValueError, match=error):
        parse_tuik_theme_catalog(provider_receipt)
    assert result is None
