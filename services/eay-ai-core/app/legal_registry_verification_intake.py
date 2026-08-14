from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .legal_promotion_gate import RelationType
from .legal_registry_discovery import (
    ConsumerRegistryManifest,
    RegistryDiscoveryCandidate,
)
from .legal_verification import VerificationCreate


_EXACT_BINDING_HOSTS = frozenset(
    {
        "resmigazete.gov.tr",
        "www.resmigazete.gov.tr",
    }
)


class RegistryBoundVerificationIntake(BaseModel):
    """Non-promoting handoff from official registry discovery to exact legal verification.

    The Ministry registry remains discovery evidence. This artifact binds that discovery to a
    separately supplied exact Resmi Gazete instrument and the dates required by the existing
    verification/promotion pipeline. Constructing the intake never verifies or promotes law.
    """

    instrument_key: str
    title: str
    registry_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_target_url: str
    discovery_url: str
    exact_binding_url: str
    exact_binding_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_date: date
    effective_from: date
    official_gazette_number: str | None = None
    relation_type: RelationType = "new"
    related_instrument_id: str | None = None
    verification: VerificationCreate
    human_review_required: Literal[True] = True
    promotion_eligible: Literal[False] = False
    auto_promote: Literal[False] = False
    intake_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _exact_binding_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("registry_verification_exact_binding_requires_https")
    if parsed.username or parsed.password:
        raise ValueError("registry_verification_exact_binding_must_not_contain_userinfo")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in _EXACT_BINDING_HOSTS:
        raise ValueError("registry_verification_exact_resmi_gazete_source_required")
    return host


def build_registry_bound_verification_intake(
    candidate: RegistryDiscoveryCandidate,
    manifest: ConsumerRegistryManifest,
    *,
    authoritative_url: str,
    authoritative_text: str,
    publication_date: date,
    effective_from: date,
    official_gazette_number: str | None = None,
    relation_type: RelationType = "new",
    related_instrument_id: str | None = None,
) -> RegistryBoundVerificationIntake:
    """Bind discovery provenance to an exact Resmi Gazete verification request fail closed.

    The returned ``VerificationCreate`` is only an intake payload. The existing verification
    store must still assess the exact publication and a later human approval is required before
    any promotion can occur.
    """

    if candidate.registry_manifest_fingerprint != manifest.manifest_fingerprint:
        raise ValueError("registry_verification_manifest_fingerprint_mismatch")
    if candidate.registry_url != str(manifest.registry_url):
        raise ValueError("registry_verification_registry_url_mismatch")
    if not candidate.discovery_only or candidate.binding_verified or candidate.promotion_eligible:
        raise ValueError("registry_verification_candidate_must_remain_discovery_only")

    instrument = next(
        (item for item in manifest.instruments if item.key == candidate.instrument_key),
        None,
    )
    if instrument is None:
        raise ValueError("registry_verification_instrument_not_in_manifest")
    if candidate.title != instrument.title:
        raise ValueError("registry_verification_title_mismatch")

    expected_target = str(instrument.registry_target_url)
    if candidate.expected_registry_target_url != expected_target:
        raise ValueError("registry_verification_expected_target_mismatch")
    if candidate.discovered_url != expected_target or not candidate.registry_target_match:
        raise ValueError("registry_verification_discovery_target_mismatch")

    _exact_binding_host(authoritative_url)
    if effective_from < publication_date:
        raise ValueError("registry_verification_effective_date_before_publication")

    verification = VerificationCreate(
        instrument_id=candidate.instrument_key,
        authoritative_url=authoritative_url,
        authoritative_text=authoritative_text,
        publication_date=publication_date,
        effective_from=effective_from,
        official_gazette_number=official_gazette_number,
        relation_type=relation_type,
        related_instrument_id=related_instrument_id,
    )
    content_sha256 = hashlib.sha256(authoritative_text.encode("utf-8")).hexdigest()
    fingerprint_payload: dict[str, object] = {
        "instrument_key": candidate.instrument_key,
        "title": candidate.title,
        "registry_manifest_fingerprint": manifest.manifest_fingerprint,
        "registry_target_url": expected_target,
        "discovery_url": candidate.discovered_url,
        "exact_binding_url": authoritative_url,
        "exact_binding_content_sha256": content_sha256,
        "publication_date": publication_date.isoformat(),
        "effective_from": effective_from.isoformat(),
        "official_gazette_number": official_gazette_number,
        "relation_type": relation_type,
        "related_instrument_id": related_instrument_id,
        "human_review_required": True,
        "promotion_eligible": False,
        "auto_promote": False,
    }

    return RegistryBoundVerificationIntake(
        instrument_key=candidate.instrument_key,
        title=candidate.title,
        registry_manifest_fingerprint=manifest.manifest_fingerprint,
        registry_target_url=expected_target,
        discovery_url=candidate.discovered_url,
        exact_binding_url=authoritative_url,
        exact_binding_content_sha256=content_sha256,
        publication_date=publication_date,
        effective_from=effective_from,
        official_gazette_number=official_gazette_number,
        relation_type=relation_type,
        related_instrument_id=related_instrument_id,
        verification=verification,
        intake_fingerprint=_canonical_fingerprint(fingerprint_payload),
    )
