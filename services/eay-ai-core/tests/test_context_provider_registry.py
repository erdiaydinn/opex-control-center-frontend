import pytest

from app.context_intelligence import ContextKind, ContextSourceClass
from app.context_provider_registry import (
    PROVIDERS,
    ContextProviderSpec,
    ProviderAccessMode,
    ProviderReadiness,
    assert_registry_fail_closed,
    require_provider,
)


def test_all_registered_providers_are_official_and_production_disabled():
    assert PROVIDERS
    assert all(provider.source_class is ContextSourceClass.OFFICIAL for provider in PROVIDERS.values())
    assert all(provider.production_enabled is False for provider in PROVIDERS.values())
    assert all(provider.continuous_ingestion_authorized is False for provider in PROVIDERS.values())
    assert_registry_fail_closed()


def test_mgm_weather_does_not_claim_an_unverified_public_api():
    provider = require_provider("tr-mgm-weather")
    assert provider.context_kinds == (ContextKind.WEATHER,)
    assert provider.access_mode is ProviderAccessMode.OFFICIAL_WEB
    assert provider.readiness is ProviderReadiness.REFERENCE_ONLY
    assert provider.exact_adapter_verified is False
    assert "public_api_contract_not_verified" in provider.notes


def test_tuik_sdmx_and_tcmb_evds_are_documented_macro_web_service_candidates():
    tuik = require_provider("tr-tuik-sdmx")
    tcmb = require_provider("tr-tcmb-evds")

    assert tuik.access_mode is ProviderAccessMode.DOCUMENTED_WEB_SERVICE
    assert tcmb.access_mode is ProviderAccessMode.DOCUMENTED_WEB_SERVICE
    assert ContextKind.MACRO_ECONOMIC in tuik.context_kinds
    assert ContextKind.MACRO_ECONOMIC in tcmb.context_kinds
    assert tcmb.requires_secret is True
    assert tuik.continuous_ingestion_authorized is False
    assert tcmb.continuous_ingestion_authorized is False
    assert tuik.production_enabled is False
    assert tcmb.production_enabled is False


def test_ibb_uym_continuous_ingestion_stays_authorization_blocked():
    provider = require_provider("istanbul-ibb-uym")

    assert provider.access_mode is ProviderAccessMode.AUTHORIZATION_REQUIRED
    assert provider.readiness is ProviderReadiness.AUTHORIZATION_BLOCKED
    assert provider.continuous_ingestion_authorized is False
    assert provider.requires_secret is True
    assert provider.production_enabled is False


def test_provider_cannot_claim_production_without_verified_adapter():
    with pytest.raises(ValueError, match="production_provider_requires_verified_adapter"):
        ContextProviderSpec(
            provider_id="fake",
            display_name="Fake",
            allowed_hosts=("example.gov.tr",),
            source_class=ContextSourceClass.OFFICIAL,
            access_mode=ProviderAccessMode.DOCUMENTED_WEB_SERVICE,
            context_kinds=(ContextKind.WEATHER,),
            exact_adapter_verified=False,
            production_enabled=True,
            readiness=ProviderReadiness.PRODUCTION_READY,
            evidence_refs=("official://fake",),
        )


def test_provider_cannot_activate_continuously_before_access_review():
    with pytest.raises(ValueError, match="production_provider_requires_continuous_access_review"):
        ContextProviderSpec(
            provider_id="authorized-only",
            display_name="Authorized Only",
            allowed_hosts=("example.gov.tr",),
            source_class=ContextSourceClass.OFFICIAL,
            access_mode=ProviderAccessMode.AUTHORIZATION_REQUIRED,
            context_kinds=(ContextKind.ROAD_CLOSURE,),
            requires_secret=True,
            continuous_ingestion_authorized=False,
            exact_adapter_verified=True,
            production_enabled=True,
            readiness=ProviderReadiness.PRODUCTION_READY,
            evidence_refs=("official://authorized",),
        )


def test_provider_hosts_must_be_hostname_only():
    with pytest.raises(ValueError, match="context_provider_host_must_be_hostname_only"):
        ContextProviderSpec(
            provider_id="bad-host",
            display_name="Bad Host",
            allowed_hosts=("https://example.com/path",),
            source_class=ContextSourceClass.OFFICIAL,
            access_mode=ProviderAccessMode.OFFICIAL_WEB,
            context_kinds=(ContextKind.WEATHER,),
            readiness=ProviderReadiness.REFERENCE_ONLY,
            evidence_refs=("official://bad",),
        )
