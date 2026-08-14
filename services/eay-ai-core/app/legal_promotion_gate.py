from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from .regulatory_authority import RegulatoryAuthorityAssessment

RelationType = Literal["new", "amends", "repeals", "supersedes"]

AUTHORITATIVE_LEGAL_HOSTS = {
    "resmigazete.gov.tr",
    "www.resmigazete.gov.tr",
    "mevzuat.gov.tr",
    "www.mevzuat.gov.tr",
}


@dataclass(frozen=True)
class LegalPromotionCandidate:
    instrument_id: str
    authoritative_url: str
    authoritative_text: str
    expected_content_sha256: str
    publication_date: date
    effective_from: date
    authority_assessment: RegulatoryAuthorityAssessment
    relation_type: RelationType = "new"
    related_instrument_id: str | None = None
    human_approval_ref: str | None = None


@dataclass(frozen=True)
class LegalPromotionDecision:
    eligible: bool
    blockers: tuple[str, ...]
    content_sha256: str
    decision_fingerprint: str
    requires_human_action: bool = True
    auto_promote: bool = False


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_legal_promotion(candidate: LegalPromotionCandidate) -> LegalPromotionDecision:
    blockers: list[str] = []
    actual_hash = hashlib.sha256(candidate.authoritative_text.encode("utf-8")).hexdigest()
    host = (urlparse(candidate.authoritative_url).hostname or "").lower()

    if host not in AUTHORITATIVE_LEGAL_HOSTS:
        blockers.append("authoritative_source_host_not_allowed")
    if actual_hash != candidate.expected_content_sha256:
        blockers.append("authoritative_text_hash_mismatch")
    if candidate.effective_from < candidate.publication_date:
        blockers.append("effective_date_before_publication")
    if candidate.authority_assessment.authority_level != "binding_candidate_unverified":
        blockers.append("exact_binding_instrument_candidate_required")
    if candidate.authority_assessment.auto_promotable_to_binding:
        blockers.append("authority_classifier_must_never_auto_promote")
    if not candidate.authority_assessment.exact_binding_verification_required:
        blockers.append("exact_binding_verification_required")
    if not candidate.human_approval_ref or len(candidate.human_approval_ref.strip()) < 3:
        blockers.append("human_approval_required")
    if candidate.relation_type != "new" and not candidate.related_instrument_id:
        blockers.append("related_instrument_required")
    if candidate.relation_type == "new" and candidate.related_instrument_id:
        blockers.append("new_instrument_must_not_reference_relation_target")

    payload = {
        "instrument_id": candidate.instrument_id,
        "authoritative_url": candidate.authoritative_url,
        "content_sha256": actual_hash,
        "publication_date": candidate.publication_date.isoformat(),
        "effective_from": candidate.effective_from.isoformat(),
        "authority_assessment_fingerprint": candidate.authority_assessment.assessment_fingerprint,
        "relation_type": candidate.relation_type,
        "related_instrument_id": candidate.related_instrument_id,
        "human_approval_ref": candidate.human_approval_ref,
        "blockers": sorted(blockers),
    }
    return LegalPromotionDecision(
        eligible=not blockers,
        blockers=tuple(sorted(blockers)),
        content_sha256=actual_hash,
        decision_fingerprint=_fingerprint(payload),
        requires_human_action=True,
        auto_promote=False,
    )


def decision_dict(decision: LegalPromotionDecision) -> dict[str, object]:
    return asdict(decision)
