import pytest

from app.enterprise_domain_registry import (
    EnterpriseDomain,
    SourceAuthority,
    classify_official_tr_source,
    require_domain_contract,
)


def test_payroll_domain_requires_temporal_deterministic_governance():
    contract = require_domain_contract(EnterpriseDomain.PAYROLL_LABOR_LAW)
    assert contract.temporal_resolution_required is True
    assert contract.deterministic_calculation_required is True
    assert contract.employee_personalization_allowed is True
    assert SourceAuthority.BINDING_LAW in contract.required_authorities
    assert SourceAuthority.COMPANY_POLICY in contract.required_authorities


def test_enterprise_domains_cover_requested_business_functions():
    assert {item.value for item in EnterpriseDomain} >= {
        "people_hr",
        "payroll_labor_law",
        "procurement",
        "planning",
        "logistics",
        "sales_commercial",
        "finance_accounting",
        "legal_compliance",
        "retail_operations",
    }


def test_official_turkish_authority_hosts_are_https_and_allowlisted():
    assert SourceAuthority.BINDING_LAW in classify_official_tr_source("https://www.mevzuat.gov.tr/example")
    assert SourceAuthority.OFFICIAL_GUIDANCE in classify_official_tr_source("https://www.sgk.gov.tr/example")
    assert SourceAuthority.OFFICIAL_GUIDANCE in classify_official_tr_source("https://www.gib.gov.tr/example")
    assert SourceAuthority.OFFICIAL_GUIDANCE in classify_official_tr_source("https://www.csgb.gov.tr/example")
    with pytest.raises(ValueError, match="enterprise_source_https_required"):
        classify_official_tr_source("http://www.sgk.gov.tr/example")
    with pytest.raises(ValueError, match="enterprise_source_host_not_authoritative"):
        classify_official_tr_source("https://example.com/law")
