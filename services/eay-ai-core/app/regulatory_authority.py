from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlparse

DocumentKind = Literal[
    "draft",
    "announcement",
    "guidance",
    "registry_entry",
    "binding_instrument_candidate",
    "unknown",
]
AuthorityLevel = Literal[
    "discovery_signal",
    "official_nonbinding",
    "official_registry",
    "binding_candidate_unverified",
]
SourceRoleValue = Literal[
    "discovery",
    "official_registry",
    "binding_publication_index",
    "guidance",
]


@dataclass(frozen=True)
class RegulatoryAuthorityAssessment:
    document_kind: DocumentKind
    authority_level: AuthorityLevel
    exact_binding_verification_required: bool
    auto_promotable_to_binding: bool
    review_reasons: tuple[str, ...]
    assessment_fingerprint: str


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(pattern.casefold() in lowered for pattern in patterns)


def _looks_like_exact_resmi_gazete_instrument(url: str, text: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    if host not in {"resmigazete.gov.tr", "www.resmigazete.gov.tr"}:
        return False
    metadata = bool(re.search(r"\b\d{1,2}\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+20\d{2}\b", text)) or bool(
        re.search(r"\bResm[îi]\s+Gazete\s+Say[ıi]\s*:\s*\d+\b", text, flags=re.IGNORECASE)
    )
    legal_structure = bool(re.search(r"\bMADDE\s+\d+\b", text, flags=re.IGNORECASE))
    return metadata and legal_structure


def assess_regulatory_authority(
    source: Any | None = None,
    *,
    source_id: str | None = None,
    source_role: SourceRoleValue | None = None,
    document_url: str,
    text: str,
) -> RegulatoryAuthorityAssessment:
    """Classify authority without importing watcher types.

    Callers may pass either the watcher's source object or explicit source_id/source_role.
    Supporting both forms keeps this module independent from regulatory.py and avoids
    circular imports while preserving a strict deterministic classification contract.
    """
    if source is not None:
        source_id = str(getattr(source, "id", source_id or ""))
        source_role = getattr(source, "role", source_role)
    if not source_id or source_role not in {
        "discovery",
        "official_registry",
        "binding_publication_index",
        "guidance",
    }:
        raise ValueError("valid_source_id_and_role_required")

    normalized = " ".join(text.split())
    reasons: list[str] = []

    if _contains_any(normalized, ("mevzuat taslağı", "tebliğ taslağı", "yönetmelik taslağı", "görüş bildirme")):
        kind: DocumentKind = "draft"
        authority: AuthorityLevel = "official_nonbinding"
        reasons.append("draft_or_public_consultation_text")
    elif source_role == "guidance" or _contains_any(normalized, ("kılavuz", "rehber", "açıklamalar")):
        kind = "guidance"
        authority = "official_nonbinding"
        reasons.append("guidance_or_explanatory_material")
    elif source_role == "official_registry":
        kind = "registry_entry"
        authority = "official_registry"
        reasons.append("official_registry_requires_exact_instrument_resolution")
    elif source_role == "binding_publication_index" and _looks_like_exact_resmi_gazete_instrument(document_url, normalized):
        kind = "binding_instrument_candidate"
        authority = "binding_candidate_unverified"
        reasons.append("exact_resmi_gazete_candidate_requires_legal_verification")
    elif source_role == "binding_publication_index":
        kind = "announcement"
        authority = "discovery_signal"
        reasons.append("publication_index_or_homepage_is_not_exact_instrument")
    elif source_role == "discovery":
        kind = "announcement"
        authority = "discovery_signal"
        reasons.append("discovery_surface_only")
    else:
        kind = "unknown"
        authority = "discovery_signal"
        reasons.append("unclassified_official_signal")

    payload = {
        "source_id": source_id,
        "source_role": source_role,
        "document_url": document_url,
        "document_kind": kind,
        "authority_level": authority,
        "review_reasons": reasons,
    }
    return RegulatoryAuthorityAssessment(
        document_kind=kind,
        authority_level=authority,
        exact_binding_verification_required=True,
        auto_promotable_to_binding=False,
        review_reasons=tuple(reasons),
        assessment_fingerprint=_fingerprint(payload),
    )


def assessment_dict(assessment: RegulatoryAuthorityAssessment) -> dict[str, object]:
    return asdict(assessment)
