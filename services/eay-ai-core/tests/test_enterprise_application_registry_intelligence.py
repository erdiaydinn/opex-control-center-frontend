import pytest

from app.enterprise_application_registry import (
    ApplicationEnvironment,
    ApplicationIdentitySource,
    AuthenticationProvider,
    EnterpriseApplicationEntry,
    load_enterprise_application_registry,
)


def test_carsiportal_is_registered_as_real_identity_but_not_live_verified():
    registry = load_enterprise_application_registry()
    carsi = registry.by_id()["yemeksepeti-carsi-portal"]

    assert carsi.environment is ApplicationEnvironment.PRODUCTION
    assert carsi.canonical_entry_url == "https://carsi-portal.yemeksepeti.com/tr/"
    assert carsi.allowed_primary_hosts == ("carsi-portal.yemeksepeti.com",)
    assert carsi.identity_source is ApplicationIdentitySource.USER_SUPPLIED
    assert carsi.authentication_provider is AuthenticationProvider.OKTA_USER_REPORTED
    assert set(carsi.reported_authentication_factors) == {"password", "email_otp"}
    assert carsi.managed_existing_browser_preferred is True
    assert carsi.read_onboarding_enabled is True
    assert carsi.write_execution_enabled is False
    assert carsi.direct_api_execution_enabled is False
    assert carsi.live_session_verified is False
    assert carsi.authoritative_readback_verified is False
    assert carsi.field_production_verified is False
    assert carsi.secrets_retained is False


def test_user_supplied_identity_cannot_self_promote_to_live_truth():
    with pytest.raises(ValueError, match="user_supplied_application_identity_cannot_claim_live_verification"):
        EnterpriseApplicationEntry(
            application_id="bad-live-claim",
            display_name="Bad",
            environment=ApplicationEnvironment.PRODUCTION,
            canonical_entry_url="https://portal.example.com/",
            allowed_primary_hosts=("portal.example.com",),
            identity_source=ApplicationIdentitySource.USER_SUPPLIED,
            live_session_verified=True,
        )


def test_production_write_and_direct_api_require_full_live_field_proof():
    with pytest.raises(ValueError, match="production_application_write_requires_live_field_proof"):
        EnterpriseApplicationEntry(
            application_id="unsafe-write",
            display_name="Unsafe",
            environment=ApplicationEnvironment.PRODUCTION,
            canonical_entry_url="https://portal.example.com/",
            allowed_primary_hosts=("portal.example.com",),
            identity_source=ApplicationIdentitySource.LIVE_OBSERVED,
            live_session_verified=True,
            authoritative_readback_verified=False,
            field_production_verified=False,
            write_execution_enabled=True,
        )

    with pytest.raises(ValueError, match="production_direct_api_requires_live_field_proof"):
        EnterpriseApplicationEntry(
            application_id="unsafe-api",
            display_name="Unsafe API",
            environment=ApplicationEnvironment.PRODUCTION,
            canonical_entry_url="https://portal.example.com/",
            allowed_primary_hosts=("portal.example.com",),
            identity_source=ApplicationIdentitySource.LIVE_OBSERVED,
            live_session_verified=True,
            authoritative_readback_verified=True,
            field_production_verified=False,
            direct_api_execution_enabled=True,
        )


def test_application_registry_rejects_query_fragments_userinfo_and_secret_retention():
    with pytest.raises(ValueError, match="enterprise_application_entry_url_must_be_secret_free"):
        EnterpriseApplicationEntry(
            application_id="query-secret",
            display_name="Query Secret",
            environment=ApplicationEnvironment.STAGING,
            canonical_entry_url="https://portal.example.com/?token=secret",
            allowed_primary_hosts=("portal.example.com",),
            identity_source=ApplicationIdentitySource.LIVE_OBSERVED,
        )

    with pytest.raises(ValueError, match="enterprise_application_registry_must_not_retain_secrets"):
        EnterpriseApplicationEntry(
            application_id="retains-secret",
            display_name="Retains secret",
            environment=ApplicationEnvironment.STAGING,
            canonical_entry_url="https://portal.example.com/",
            allowed_primary_hosts=("portal.example.com",),
            identity_source=ApplicationIdentitySource.LIVE_OBSERVED,
            secrets_retained=True,
        )
