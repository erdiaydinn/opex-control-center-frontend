"""Governed provider registry for EAY Jarvis external context.

The registry records what is actually verified about external data sources and
keeps production activation fail-closed. A provider entry is not proof that a
live adapter, credential or continuous-use authorization exists.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .context_intelligence import ContextKind, ContextSourceClass

CONTEXT_PROVIDER_REGISTRY_CONTRACT = "eay-context-provider-registry-v1"


class ProviderAccessMode(str, Enum):
    OFFICIAL_WEB = "official_web"
    DOCUMENTED_WEB_SERVICE = "documented_web_service"
    AUTHORIZATION_REQUIRED = "authorization_required"


class ProviderReadiness(str, Enum):
    REFERENCE_ONLY = "reference_only"
    ADAPTER_READY_TO_BUILD = "adapter_ready_to_build"
    FIELD_VERIFIED_ONE_SHOT = "field_verified_one_shot"
    AUTHORIZATION_BLOCKED = "authorization_blocked"
    PRODUCTION_READY = "production_ready"


class ContextProviderSpec(BaseModel):
    contract: str = CONTEXT_PROVIDER_REGISTRY_CONTRACT
    provider_id: str = Field(min_length=1, max_length=180)
    display_name: str = Field(min_length=1, max_length=300)
    allowed_hosts: tuple[str, ...] = Field(min_length=1)
    source_class: ContextSourceClass
    access_mode: ProviderAccessMode
    context_kinds: tuple[ContextKind, ...] = Field(min_length=1)
    requires_secret: bool = False
    one_shot_observation_authorized: bool = False
    continuous_ingestion_authorized: bool = False
    exact_adapter_verified: bool = False
    production_enabled: bool = False
    readiness: ProviderReadiness
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_fail_closed_activation(self) -> ContextProviderSpec:
        normalized_hosts = [host.casefold().strip().rstrip(".") for host in self.allowed_hosts]
        if any(not host or "://" in host or "/" in host or "@" in host for host in normalized_hosts):
            raise ValueError("context_provider_host_must_be_hostname_only")
        if len(set(normalized_hosts)) != len(normalized_hosts):
            raise ValueError("context_provider_duplicate_host")
        if self.one_shot_observation_authorized and not self.exact_adapter_verified:
            raise ValueError("one_shot_provider_requires_verified_adapter")
        if self.readiness is ProviderReadiness.FIELD_VERIFIED_ONE_SHOT and (
            not self.one_shot_observation_authorized or not self.exact_adapter_verified
        ):
            raise ValueError("field_verified_provider_requires_one_shot_adapter")
        if self.production_enabled:
            if not self.exact_adapter_verified:
                raise ValueError("production_provider_requires_verified_adapter")
            if not self.one_shot_observation_authorized:
                raise ValueError("production_provider_requires_one_shot_authority")
            if not self.continuous_ingestion_authorized:
                raise ValueError("production_provider_requires_continuous_access_review")
            if self.access_mode is ProviderAccessMode.AUTHORIZATION_REQUIRED and not self.requires_secret:
                raise ValueError("authorized_provider_secret_contract_required")
            if self.readiness is not ProviderReadiness.PRODUCTION_READY:
                raise ValueError("production_provider_requires_production_ready_state")
        if self.readiness is ProviderReadiness.PRODUCTION_READY and not self.exact_adapter_verified:
            raise ValueError("production_ready_provider_requires_verified_adapter")
        return self


PROVIDERS: dict[str, ContextProviderSpec] = {
    "tr-mgm-weather": ContextProviderSpec(
        provider_id="tr-mgm-weather",
        display_name="Meteoroloji Genel Müdürlüğü",
        allowed_hosts=("mgm.gov.tr", "www.mgm.gov.tr"),
        source_class=ContextSourceClass.OFFICIAL,
        access_mode=ProviderAccessMode.OFFICIAL_WEB,
        context_kinds=(ContextKind.WEATHER,),
        continuous_ingestion_authorized=False,
        exact_adapter_verified=False,
        production_enabled=False,
        readiness=ProviderReadiness.REFERENCE_ONLY,
        evidence_refs=("official://mgm/hourly-forecast",),
        notes=(
            "official_hourly_forecast_verified",
            "public_api_contract_not_verified",
            "do_not_scrape_continuously_without_approved_access_contract",
        ),
    ),
    "tr-tuik-theme-catalog": ContextProviderSpec(
        provider_id="tr-tuik-theme-catalog",
        display_name="Türkiye İstatistik Kurumu Veri Portalı Tema Kataloğu",
        allowed_hosts=("veriportali.tuik.gov.tr",),
        source_class=ContextSourceClass.OFFICIAL,
        access_mode=ProviderAccessMode.OFFICIAL_WEB,
        context_kinds=(ContextKind.MACRO_ECONOMIC,),
        one_shot_observation_authorized=True,
        continuous_ingestion_authorized=False,
        exact_adapter_verified=True,
        production_enabled=False,
        readiness=ProviderReadiness.FIELD_VERIFIED_ONE_SHOT,
        evidence_refs=(
            "field://tuik/theme-catalog/session-aware-2026-08-21",
            "field://tuik/theme-catalog/schema-2026-08-22",
        ),
        notes=(
            "official_portal_theme_catalog_field_verified",
            "session_bootstrap_required_before_theme_json_read",
            "one_shot_read_only_observation_authorized",
            "continuous_scheduler_not_authorized",
            "theme_catalog_is_external_context_not_company_truth",
        ),
    ),
    "tr-tuik-sdmx": ContextProviderSpec(
        provider_id="tr-tuik-sdmx",
        display_name="Türkiye İstatistik Kurumu SDMX",
        allowed_hosts=("veriportali.tuik.gov.tr",),
        source_class=ContextSourceClass.OFFICIAL,
        access_mode=ProviderAccessMode.DOCUMENTED_WEB_SERVICE,
        context_kinds=(ContextKind.MACRO_ECONOMIC,),
        continuous_ingestion_authorized=False,
        exact_adapter_verified=False,
        production_enabled=False,
        readiness=ProviderReadiness.ADAPTER_READY_TO_BUILD,
        evidence_refs=("official://tuik/sdmx-web-service",),
        notes=(
            "sdmx_service_documented",
            "bulk_csv_xml_json_documented",
            "continuous_use_terms_must_be_verified_before_scheduler_activation",
        ),
    ),
    "tr-tcmb-evds": ContextProviderSpec(
        provider_id="tr-tcmb-evds",
        display_name="TCMB Elektronik Veri Dağıtım Sistemi",
        allowed_hosts=("evds3.tcmb.gov.tr",),
        source_class=ContextSourceClass.OFFICIAL,
        access_mode=ProviderAccessMode.DOCUMENTED_WEB_SERVICE,
        context_kinds=(ContextKind.MACRO_ECONOMIC,),
        requires_secret=True,
        continuous_ingestion_authorized=False,
        exact_adapter_verified=False,
        production_enabled=False,
        readiness=ProviderReadiness.ADAPTER_READY_TO_BUILD,
        evidence_refs=("official://tcmb/evds-web-service-guide",),
        notes=(
            "web_service_guide_verified",
            "runtime_secret_required_before_live_calls",
            "continuous_use_terms_must_be_verified_before_scheduler_activation",
        ),
    ),
    "istanbul-ibb-uym": ContextProviderSpec(
        provider_id="istanbul-ibb-uym",
        display_name="İBB Ulaşım Yönetim Merkezi Trafik Yoğunluk Haritası",
        allowed_hosts=("uym.ibb.gov.tr",),
        source_class=ContextSourceClass.OFFICIAL,
        access_mode=ProviderAccessMode.AUTHORIZATION_REQUIRED,
        context_kinds=(
            ContextKind.ROAD_CLOSURE,
            ContextKind.TRANSIT_DISRUPTION,
            ContextKind.LOCAL_INCIDENT,
            ContextKind.WEATHER,
        ),
        requires_secret=True,
        continuous_ingestion_authorized=False,
        exact_adapter_verified=False,
        production_enabled=False,
        readiness=ProviderReadiness.AUTHORIZATION_BLOCKED,
        evidence_refs=("official://ibb-uym/traffic-map", "official://ibb-uym/continuous-access-terms"),
        notes=(
            "traffic_weather_and_road_context_verified",
            "continuous_7x24_access_requires_official_application_and_authorized_credentials",
        ),
    ),
}


def require_provider(provider_id: str) -> ContextProviderSpec:
    try:
        return PROVIDERS[provider_id]
    except KeyError as exc:
        raise ValueError("context_provider_unknown") from exc


def assert_registry_fail_closed() -> None:
    if any(provider.production_enabled for provider in PROVIDERS.values()):
        raise ValueError("context_provider_registry_unapproved_production_activation")
