import pytest

from app.context_provider_gateway import RequestPurpose, plan_provider_request


def test_mgm_one_shot_plan_is_safe_but_not_executable_before_adapter_verification():
    plan = plan_provider_request(
        provider_id="tr-mgm-weather",
        url="https://www.mgm.gov.tr/tahmin/saatlik.aspx?m=ISTANBUL",
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
    )

    assert plan.execution_permitted is False
    assert "provider_exact_adapter_not_verified" in plan.blockers
    assert "provider_production_not_enabled" in plan.blockers


def test_ibb_continuous_plan_requires_secret_authorization_and_continuous_access_review():
    plan = plan_provider_request(
        provider_id="istanbul-ibb-uym",
        url="https://uym.ibb.gov.tr/tyh/tyhar.aspx",
        purpose=RequestPurpose.CONTINUOUS_INGESTION,
    )

    assert plan.execution_permitted is False
    assert "provider_secret_reference_missing" in plan.blockers
    assert "provider_authorization_evidence_missing" in plan.blockers
    assert "provider_continuous_ingestion_not_authorized" in plan.blockers


def test_tcmb_secret_must_be_referenced_not_embedded_in_query():
    with pytest.raises(ValueError, match="provider_request_secret_in_query_forbidden"):
        plan_provider_request(
            provider_id="tr-tcmb-evds",
            url="https://evds3.tcmb.gov.tr/service?api_key=secret",
            purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
            secret_ref="secret://tcmb/evds",
        )


def test_arbitrary_host_is_rejected_even_for_registered_provider():
    with pytest.raises(ValueError, match="provider_request_host_not_allowlisted"):
        plan_provider_request(
            provider_id="tr-tuik-sdmx",
            url="https://attacker.example/steal",
            purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        )


def test_http_ip_literal_userinfo_and_nonstandard_port_are_rejected():
    with pytest.raises(ValueError, match="provider_request_https_required"):
        plan_provider_request(
            provider_id="tr-mgm-weather",
            url="http://www.mgm.gov.tr/tahmin/saatlik.aspx",
            purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        )

    with pytest.raises(ValueError, match="provider_request_ip_literal_forbidden"):
        plan_provider_request(
            provider_id="tr-mgm-weather",
            url="https://127.0.0.1/test",
            purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        )

    with pytest.raises(ValueError, match="provider_request_userinfo_forbidden"):
        plan_provider_request(
            provider_id="tr-mgm-weather",
            url="https://user:pass@www.mgm.gov.tr/test",
            purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        )

    with pytest.raises(ValueError, match="provider_request_nonstandard_port_forbidden"):
        plan_provider_request(
            provider_id="tr-mgm-weather",
            url="https://www.mgm.gov.tr:8443/test",
            purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
        )
