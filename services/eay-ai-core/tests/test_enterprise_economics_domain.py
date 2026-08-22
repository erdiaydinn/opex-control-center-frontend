from app.enterprise_domain_registry import (
    EnterpriseDomain,
    SourceAuthority,
    classify_official_tr_source,
    require_domain_contract,
)


def test_economics_market_domain_requires_official_economic_and_governed_operational_truth():
    contract = require_domain_contract(EnterpriseDomain.ECONOMICS_MARKET)

    assert contract.temporal_resolution_required is True
    assert contract.deterministic_calculation_required is True
    assert contract.employee_personalization_allowed is False
    assert SourceAuthority.OFFICIAL_ECONOMIC_DATA in contract.required_authorities
    assert SourceAuthority.GOVERNED_OPERATIONAL_DATA in contract.required_authorities


def test_tcmb_and_tuik_are_economic_authority_not_binding_law():
    for url in (
        "https://www.tcmb.gov.tr/example",
        "https://veriportali.tuik.gov.tr/example",
    ):
        authorities = classify_official_tr_source(url)
        assert SourceAuthority.OFFICIAL_ECONOMIC_DATA in authorities
        assert SourceAuthority.BINDING_LAW not in authorities


def test_existing_finance_sales_legal_and_operations_domains_remain_present():
    assert {item.value for item in EnterpriseDomain} >= {
        "sales_commercial",
        "finance_accounting",
        "economics_market",
        "legal_compliance",
        "retail_operations",
    }
