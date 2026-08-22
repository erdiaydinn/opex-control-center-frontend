"""Supply-chain threat matching and CRA reporting-decision governance.

External malicious-package/vulnerability intelligence is evidence, not EAY truth.
This module only derives review/reportability decisions from independently governed
company scope and occurrence evidence. It never submits a regulatory report or
creates execution authority.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

CYBER_SUPPLY_CHAIN_REGULATORY_CONTRACT = "eay-cyber-supply-chain-regulatory-v1"
CRA_REPORTING_START = datetime(2026, 9, 11, tzinfo=UTC)


class SupplyChainThreatType(str, Enum):
    VULNERABILITY = "vulnerability"
    MALICIOUS_PACKAGE = "malicious_package"


class PackageCoordinate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystem: str = Field(min_length=1, max_length=64)
    package_name: str = Field(min_length=1, max_length=256)
    exact_version: str = Field(min_length=1, max_length=128)

    @property
    def normalized_key(self) -> tuple[str, str, str]:
        return (
            self.ecosystem.strip().lower(),
            self.package_name.strip().lower(),
            self.exact_version.strip(),
        )


class ExternalSupplyChainObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_SUPPLY_CHAIN_REGULATORY_CONTRACT
    source_id: str = Field(min_length=1, max_length=80)
    record_id: str = Field(min_length=1, max_length=160)
    threat_type: SupplyChainThreatType
    package: PackageCoordinate
    observed_at: datetime
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_exposure_authority: bool = False
    incident_confirmation_authority: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def external_observation_never_grants_company_authority(
        self,
    ) -> ExternalSupplyChainObservation:
        if any(
            (
                self.company_exposure_authority,
                self.incident_confirmation_authority,
                self.execution_authority_granted,
            )
        ):
            raise ValueError("external_supply_chain_intel_never_grants_eay_authority")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at_must_be_timezone_aware")
        return self


class GovernedDependencyComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1)
    inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    package: PackageCoordinate
    inventory_verified: bool
    production_deployment_verified: bool = False


class SupplyChainMatchStatus(str, Enum):
    NO_EXACT_MATCH = "no_exact_match"
    INVENTORY_MATCH_REVIEW_REQUIRED = "inventory_match_review_required"
    PRODUCTION_EXPOSURE_REVIEW_REQUIRED = "production_exposure_review_required"


class SupplyChainMatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SupplyChainMatchStatus
    exact_package_match: bool
    inventory_verified: bool
    production_deployment_verified: bool
    eay_affected_claim_allowed: bool = False
    incident_claim_allowed: bool = False
    execution_authority_granted: bool = False
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")



def match_supply_chain_observation(
    observation: ExternalSupplyChainObservation,
    component: GovernedDependencyComponent,
) -> SupplyChainMatchDecision:
    exact_match = observation.package.normalized_key == component.package.normalized_key
    if not exact_match:
        status = SupplyChainMatchStatus.NO_EXACT_MATCH
    elif component.inventory_verified and component.production_deployment_verified:
        status = SupplyChainMatchStatus.PRODUCTION_EXPOSURE_REVIEW_REQUIRED
    else:
        status = SupplyChainMatchStatus.INVENTORY_MATCH_REVIEW_REQUIRED

    return SupplyChainMatchDecision(
        status=status,
        exact_package_match=exact_match,
        inventory_verified=component.inventory_verified,
        production_deployment_verified=component.production_deployment_verified,
        evidence_fingerprint=_sha256(
            {
                "observation": observation.model_dump(mode="json"),
                "component": component.model_dump(mode="json"),
                "status": status.value,
            }
        ),
    )


class CraOccurrenceType(str, Enum):
    ACTIVELY_EXPLOITED_VULNERABILITY = "actively_exploited_vulnerability"
    SEVERE_INCIDENT = "severe_incident"


class CraProductScope(str, Enum):
    UNKNOWN = "unknown"
    OUT_OF_SCOPE = "out_of_scope"
    IN_SCOPE = "in_scope"


class CraEvidenceState(str, Enum):
    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class CraReportabilityStatus(str, Enum):
    NOT_YET_APPLICABLE = "not_yet_applicable"
    HOLD_COMPANY_IMPACT_UNVERIFIED = "hold_company_impact_unverified"
    HOLD_ACTIVE_EXPLOITATION_UNVERIFIED = "hold_active_exploitation_unverified"
    HOLD_PRODUCT_SCOPE_UNKNOWN = "hold_product_scope_unknown"
    OUT_OF_SCOPE = "out_of_scope"
    HUMAN_REPORTING_REVIEW_REQUIRED = "human_reporting_review_required"


class CraReportabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurrence_type: CraOccurrenceType
    awareness_at: datetime
    company_impact: CraEvidenceState
    active_exploitation: CraEvidenceState = CraEvidenceState.UNKNOWN
    product_scope: CraProductScope
    corrective_measure_available_at: datetime | None = None

    @model_validator(mode="after")
    def timestamps_are_timezone_aware(self) -> CraReportabilityInput:
        if self.awareness_at.tzinfo is None:
            raise ValueError("awareness_at_must_be_timezone_aware")
        if (
            self.corrective_measure_available_at is not None
            and self.corrective_measure_available_at.tzinfo is None
        ):
            raise ValueError("corrective_measure_available_at_must_be_timezone_aware")
        return self


class CraReportingClock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    early_warning_due_at: datetime
    notification_due_at: datetime
    final_report_due_at: datetime | None


class CraReportabilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CraReportabilityStatus
    reportable_candidate: bool
    reporting_clock: CraReportingClock | None
    human_approval_required: bool = True
    automatic_submission_permitted: bool = False
    execution_authority_granted: bool = False
    decision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")



def assess_cra_reportability(value: CraReportabilityInput) -> CraReportabilityDecision:
    awareness = value.awareness_at.astimezone(UTC)
    status: CraReportabilityStatus
    clock: CraReportingClock | None = None

    if awareness < CRA_REPORTING_START:
        status = CraReportabilityStatus.NOT_YET_APPLICABLE
    elif value.company_impact is not CraEvidenceState.VERIFIED:
        status = CraReportabilityStatus.HOLD_COMPANY_IMPACT_UNVERIFIED
    elif (
        value.occurrence_type is CraOccurrenceType.ACTIVELY_EXPLOITED_VULNERABILITY
        and value.active_exploitation is not CraEvidenceState.VERIFIED
    ):
        status = CraReportabilityStatus.HOLD_ACTIVE_EXPLOITATION_UNVERIFIED
    elif value.product_scope is CraProductScope.UNKNOWN:
        status = CraReportabilityStatus.HOLD_PRODUCT_SCOPE_UNKNOWN
    elif value.product_scope is CraProductScope.OUT_OF_SCOPE:
        status = CraReportabilityStatus.OUT_OF_SCOPE
    else:
        status = CraReportabilityStatus.HUMAN_REPORTING_REVIEW_REQUIRED
        final_due: datetime | None
        if value.occurrence_type is CraOccurrenceType.ACTIVELY_EXPLOITED_VULNERABILITY:
            corrective = value.corrective_measure_available_at
            final_due = (
                corrective.astimezone(UTC) + timedelta(days=14)
                if corrective is not None
                else None
            )
        else:
            final_due = _add_calendar_month(awareness + timedelta(hours=72))
        clock = CraReportingClock(
            early_warning_due_at=awareness + timedelta(hours=24),
            notification_due_at=awareness + timedelta(hours=72),
            final_report_due_at=final_due,
        )

    reportable_candidate = status is CraReportabilityStatus.HUMAN_REPORTING_REVIEW_REQUIRED
    return CraReportabilityDecision(
        status=status,
        reportable_candidate=reportable_candidate,
        reporting_clock=clock,
        decision_fingerprint=_sha256(
            {
                "input": value.model_dump(mode="json"),
                "status": status.value,
                "reportable_candidate": reportable_candidate,
                "clock": clock.model_dump(mode="json") if clock else None,
            }
        ),
    )


def _add_calendar_month(value: datetime) -> datetime:
    year = value.year + (value.month // 12)
    month = 1 if value.month == 12 else value.month + 1
    if value.month != 12:
        year = value.year
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
