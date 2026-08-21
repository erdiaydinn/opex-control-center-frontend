from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .schemas import ActionPriority, ActionRisk, StrictModel

ReportTemplate = Literal[
    "EXECUTIVE_SUMMARY",
    "STANDARD_AUDIT",
    "EVIDENCE_REGULATORY_PACK",
]
RecipientSource = Literal[
    "USER",
    "GROUP",
    "LOCATION_MANAGER",
    "LOCATION_CONTACT",
    "MANUAL_EMAIL",
]

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuditReportFact(StrictModel):
    fact_id: str = Field(min_length=1, max_length=180)
    label: str = Field(min_length=1, max_length=240)
    value: str = Field(min_length=1, max_length=2000)
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_refs(self) -> AuditReportFact:
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("report fact source_refs must be unique")
        return self


class AuditReportFinding(StrictModel):
    finding_id: str = Field(min_length=1, max_length=180)
    item_key: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=500)
    risk_class: ActionRisk
    priority: ActionPriority
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=50)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=50)
    privacy_verified_evidence_refs: tuple[str, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def validate_evidence_privacy(self) -> AuditReportFinding:
        evidence = set(self.evidence_refs)
        verified = set(self.privacy_verified_evidence_refs)
        if not verified.issubset(evidence):
            raise ValueError("privacy-verified evidence refs must be finding evidence refs")
        if evidence != verified:
            raise ValueError(
                "reports may expose only privacy-verified governed evidence refs"
            )
        return self


class AuditReportSnapshot(StrictModel):
    audit_run_id: str = Field(min_length=1, max_length=180)
    location_id: str = Field(min_length=1, max_length=180)
    location_display_name: str = Field(min_length=1, max_length=300)
    audit_title: str = Field(min_length=1, max_length=300)
    audited_at: datetime
    completed_at: datetime | None = None
    completion_state: Literal["COMPLETE", "INCOMPLETE"]
    final_score_pct: float | None = Field(default=None, ge=0, le=100)
    provisional_score_pct: float | None = Field(default=None, ge=0, le=100)
    pass_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    insufficient_evidence_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    facts: tuple[AuditReportFact, ...] = Field(default=(), max_length=200)
    findings: tuple[AuditReportFinding, ...] = Field(default=(), max_length=500)

    @model_validator(mode="after")
    def validate_score_truth(self) -> AuditReportSnapshot:
        if self.completion_state == "COMPLETE" and self.final_score_pct is None:
            raise ValueError("complete reports require final_score_pct")
        if self.completion_state == "INCOMPLETE" and self.final_score_pct is not None:
            raise ValueError("incomplete reports cannot publish a final score")
        return self


class AuditReportArtifact(StrictModel):
    template: ReportTemplate
    subject: str
    executive_summary: str
    snapshot: AuditReportSnapshot
    source_fact_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def _priority_rank(priority: ActionPriority) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}[priority]


def render_executive_summary(snapshot: AuditReportSnapshot, *, locale: str = "tr") -> str:
    """Build a deterministic summary. No LLM may add facts to this authority surface."""

    ordered_findings = sorted(
        snapshot.findings,
        key=lambda finding: (_priority_rank(finding.priority), finding.finding_id),
    )
    top_findings = ordered_findings[:5]
    score_label = (
        f"%{snapshot.final_score_pct:.2f}"
        if snapshot.final_score_pct is not None
        else "final score unavailable"
    )

    if locale.lower().startswith("tr"):
        header = (
            f"{snapshot.location_display_name} için {snapshot.audit_title} denetimi "
            f"{snapshot.completion_state.lower()} durumundadır. "
            f"Skor: {score_label}. "
            f"PASS {snapshot.pass_count}, FAIL {snapshot.fail_count}, "
            f"N/A {snapshot.not_applicable_count}, yetersiz kanıt "
            f"{snapshot.insufficient_evidence_count}, inceleme gerekli "
            f"{snapshot.review_required_count}."
        )
        if not top_findings:
            return header
        bullets = "; ".join(
            f"{finding.priority.upper()}: {finding.title}" for finding in top_findings
        )
        return f"{header} Öncelikli bulgular: {bullets}."

    header = (
        f"{snapshot.audit_title} for {snapshot.location_display_name} is "
        f"{snapshot.completion_state.lower()}. Score: {score_label}. "
        f"PASS {snapshot.pass_count}, FAIL {snapshot.fail_count}, "
        f"N/A {snapshot.not_applicable_count}, insufficient evidence "
        f"{snapshot.insufficient_evidence_count}, review required "
        f"{snapshot.review_required_count}."
    )
    if not top_findings:
        return header
    bullets = "; ".join(
        f"{finding.priority.upper()}: {finding.title}" for finding in top_findings
    )
    return f"{header} Priority findings: {bullets}."


def build_report_artifact(
    snapshot: AuditReportSnapshot,
    *,
    template: ReportTemplate,
    locale: str = "tr",
) -> AuditReportArtifact:
    source_fact_ids = tuple(fact.fact_id for fact in snapshot.facts)
    finding_ids = tuple(finding.finding_id for finding in snapshot.findings)
    evidence_refs = tuple(
        sorted(
            {
                ref
                for finding in snapshot.findings
                for ref in finding.privacy_verified_evidence_refs
            }
        )
    )
    score = (
        f"%{snapshot.final_score_pct:.2f}"
        if snapshot.final_score_pct is not None
        else "INCOMPLETE"
    )
    subject = (
        f"[EAY Audit] {snapshot.location_display_name} | "
        f"{snapshot.completion_state} | {score} | {snapshot.fail_count} bulgu"
        if locale.lower().startswith("tr")
        else (
            f"[EAY Audit] {snapshot.location_display_name} | "
            f"{snapshot.completion_state} | {score} | {snapshot.fail_count} findings"
        )
    )
    return AuditReportArtifact(
        template=template,
        subject=subject,
        executive_summary=render_executive_summary(snapshot, locale=locale),
        snapshot=snapshot,
        source_fact_ids=source_fact_ids,
        finding_ids=finding_ids,
        evidence_refs=evidence_refs,
    )


class AuditReportRecipient(StrictModel):
    source: RecipientSource
    recipient_key: str = Field(min_length=1, max_length=320)
    email: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def validate_email(self) -> AuditReportRecipient:
        if self.email is not None and not _EMAIL_PATTERN.fullmatch(self.email):
            raise ValueError("invalid report recipient email")
        if (
            self.source == "MANUAL_EMAIL"
            and (self.email is None or self.recipient_key != self.email)
        ):
            raise ValueError("manual email recipient must bind key to exact email")
        return self


class AuditReportDistributionRequest(StrictModel):
    template: ReportTemplate
    recipients: tuple[AuditReportRecipient, ...] = Field(min_length=1, max_length=100)
    manual_recipient_authorized: bool = False
    include_evidence_thumbnails: bool = False

    @model_validator(mode="after")
    def validate_distribution(self) -> AuditReportDistributionRequest:
        if (
            any(recipient.source == "MANUAL_EMAIL" for recipient in self.recipients)
            and not self.manual_recipient_authorized
        ):
            raise ValueError("manual report recipients require explicit authorization")
        identities = tuple(
            (recipient.source, recipient.recipient_key, recipient.email)
            for recipient in self.recipients
        )
        if len(set(identities)) != len(identities):
            raise ValueError("report recipients must be unique")
        return self


class AuditReportDeliveryTarget(StrictModel):
    recipient_source: RecipientSource
    recipient_key: str
    email: str | None


class AuditReportDistributionPlan(StrictModel):
    template: ReportTemplate
    targets: tuple[AuditReportDeliveryTarget, ...]
    include_evidence_thumbnails: bool
    requires_private_link_delivery: bool = True
    raw_media_attachment_allowed: bool = False


def build_distribution_plan(
    request: AuditReportDistributionRequest,
) -> AuditReportDistributionPlan:
    """Resolve a governed plan. Actual email transport remains an injected authority."""

    return AuditReportDistributionPlan(
        template=request.template,
        targets=tuple(
            AuditReportDeliveryTarget(
                recipient_source=recipient.source,
                recipient_key=recipient.recipient_key,
                email=recipient.email,
            )
            for recipient in request.recipients
        ),
        include_evidence_thumbnails=request.include_evidence_thumbnails,
    )
