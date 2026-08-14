from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class EnterpriseDomain(str, Enum):
    PEOPLE_HR = "people_hr"
    PAYROLL_LABOR_LAW = "payroll_labor_law"
    PROCUREMENT = "procurement"
    PLANNING = "planning"
    LOGISTICS = "logistics"
    SALES_COMMERCIAL = "sales_commercial"
    FINANCE_ACCOUNTING = "finance_accounting"
    LEGAL_COMPLIANCE = "legal_compliance"
    RETAIL_OPERATIONS = "retail_operations"


class SourceAuthority(str, Enum):
    BINDING_LAW = "binding_law"
    OFFICIAL_GUIDANCE = "official_guidance"
    COMPANY_POLICY = "company_policy"
    GOVERNED_OPERATIONAL_DATA = "governed_operational_data"
    EMPLOYEE_RECORD = "employee_record"


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# These are authority allow-list entries, not a claim that every page on the host is
# binding law. Existing legal verification/temporal gates still decide instrument status.
OFFICIAL_TR_AUTHORITY_HOSTS: dict[str, tuple[SourceAuthority, ...]] = {
    "resmigazete.gov.tr": (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE),
    "www.resmigazete.gov.tr": (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE),
    "mevzuat.gov.tr": (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE),
    "www.mevzuat.gov.tr": (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE),
    "csgb.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
    "www.csgb.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
    "sgk.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
    "www.sgk.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
    "e.sgk.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
    "gib.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
    "www.gib.gov.tr": (SourceAuthority.OFFICIAL_GUIDANCE,),
}


@dataclass(frozen=True)
class DomainContract:
    domain: EnterpriseDomain
    required_authorities: tuple[SourceAuthority, ...]
    temporal_resolution_required: bool
    deterministic_calculation_required: bool
    employee_personalization_allowed: bool
    fingerprint: str

    def validate(self) -> None:
        if not self.required_authorities:
            raise ValueError("enterprise_domain_authority_required")
        payload = {
            "domain": self.domain.value,
            "required_authorities": tuple(item.value for item in self.required_authorities),
            "temporal_resolution_required": self.temporal_resolution_required,
            "deterministic_calculation_required": self.deterministic_calculation_required,
            "employee_personalization_allowed": self.employee_personalization_allowed,
        }
        if _sha256(payload) != self.fingerprint:
            raise ValueError("enterprise_domain_contract_fingerprint_drift")


def _contract(
    domain: EnterpriseDomain,
    authorities: tuple[SourceAuthority, ...],
    *,
    temporal: bool,
    deterministic: bool,
    employee: bool,
) -> DomainContract:
    payload = {
        "domain": domain.value,
        "required_authorities": tuple(item.value for item in authorities),
        "temporal_resolution_required": temporal,
        "deterministic_calculation_required": deterministic,
        "employee_personalization_allowed": employee,
    }
    contract = DomainContract(
        domain=domain,
        required_authorities=authorities,
        temporal_resolution_required=temporal,
        deterministic_calculation_required=deterministic,
        employee_personalization_allowed=employee,
        fingerprint=_sha256(payload),
    )
    contract.validate()
    return contract


DOMAIN_CONTRACTS: dict[EnterpriseDomain, DomainContract] = {
    EnterpriseDomain.PEOPLE_HR: _contract(
        EnterpriseDomain.PEOPLE_HR,
        (SourceAuthority.COMPANY_POLICY, SourceAuthority.EMPLOYEE_RECORD),
        temporal=True,
        deterministic=False,
        employee=True,
    ),
    EnterpriseDomain.PAYROLL_LABOR_LAW: _contract(
        EnterpriseDomain.PAYROLL_LABOR_LAW,
        (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE, SourceAuthority.COMPANY_POLICY),
        temporal=True,
        deterministic=True,
        employee=True,
    ),
    EnterpriseDomain.PROCUREMENT: _contract(
        EnterpriseDomain.PROCUREMENT,
        (SourceAuthority.COMPANY_POLICY, SourceAuthority.GOVERNED_OPERATIONAL_DATA),
        temporal=True,
        deterministic=True,
        employee=False,
    ),
    EnterpriseDomain.PLANNING: _contract(
        EnterpriseDomain.PLANNING,
        (SourceAuthority.COMPANY_POLICY, SourceAuthority.GOVERNED_OPERATIONAL_DATA),
        temporal=True,
        deterministic=True,
        employee=False,
    ),
    EnterpriseDomain.LOGISTICS: _contract(
        EnterpriseDomain.LOGISTICS,
        (SourceAuthority.COMPANY_POLICY, SourceAuthority.GOVERNED_OPERATIONAL_DATA),
        temporal=True,
        deterministic=True,
        employee=False,
    ),
    EnterpriseDomain.SALES_COMMERCIAL: _contract(
        EnterpriseDomain.SALES_COMMERCIAL,
        (SourceAuthority.COMPANY_POLICY, SourceAuthority.GOVERNED_OPERATIONAL_DATA),
        temporal=True,
        deterministic=True,
        employee=False,
    ),
    EnterpriseDomain.FINANCE_ACCOUNTING: _contract(
        EnterpriseDomain.FINANCE_ACCOUNTING,
        (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE, SourceAuthority.COMPANY_POLICY),
        temporal=True,
        deterministic=True,
        employee=False,
    ),
    EnterpriseDomain.LEGAL_COMPLIANCE: _contract(
        EnterpriseDomain.LEGAL_COMPLIANCE,
        (SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE, SourceAuthority.COMPANY_POLICY),
        temporal=True,
        deterministic=False,
        employee=False,
    ),
    EnterpriseDomain.RETAIL_OPERATIONS: _contract(
        EnterpriseDomain.RETAIL_OPERATIONS,
        (SourceAuthority.COMPANY_POLICY, SourceAuthority.GOVERNED_OPERATIONAL_DATA),
        temporal=True,
        deterministic=True,
        employee=False,
    ),
}


def classify_official_tr_source(url: str) -> tuple[SourceAuthority, ...]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("enterprise_source_https_required")
    host = (parsed.hostname or "").lower()
    authorities = OFFICIAL_TR_AUTHORITY_HOSTS.get(host)
    if authorities is None:
        raise ValueError("enterprise_source_host_not_authoritative")
    return authorities


def require_domain_contract(domain: EnterpriseDomain | str) -> DomainContract:
    try:
        key = EnterpriseDomain(domain)
    except ValueError as exc:
        raise ValueError("enterprise_domain_unknown") from exc
    return DOMAIN_CONTRACTS[key]
