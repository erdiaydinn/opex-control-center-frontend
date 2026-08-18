from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DeliveryMode = Literal["hls", "dash"]


@dataclass(frozen=True)
class MediaTranscodeSpec:
    private_source_key: str
    delivery_key: str
    delivery_mode: DeliveryMode
    renditions: tuple[int, ...]
    drm_policy: str


@dataclass(frozen=True)
class MediaLoadEvidence:
    concurrent_sessions: int
    environment: str
    evidence_class: str
    measured: bool
    provenance: str


def build_transcode_spec(
    *,
    private_source_key: str,
    delivery_key: str,
    delivery_mode: DeliveryMode,
    renditions: tuple[int, ...] = (360, 720, 1080),
    drm_policy: str = "short-lived-token",
) -> MediaTranscodeSpec:
    if not private_source_key.strip() or private_source_key.startswith(("http://", "https://")):
        raise ValueError(
            "Academy transcode source must be a private object-storage key, not a public URL"
        )
    if not delivery_key.strip() or ".." in delivery_key:
        raise ValueError("invalid Academy delivery key")

    ordered = tuple(sorted(set(renditions)))
    if not ordered or any(height < 240 or height > 2160 for height in ordered):
        raise ValueError("invalid rendition ladder")
    return MediaTranscodeSpec(
        private_source_key=private_source_key,
        delivery_key=delivery_key,
        delivery_mode=delivery_mode,
        renditions=ordered,
        drm_policy=drm_policy,
    )


def production_media_capacity_accepted(evidence: MediaLoadEvidence) -> bool:
    return (
        evidence.concurrent_sessions >= 1200
        and evidence.evidence_class == "REAL_MEDIA_ENVIRONMENT"
        and evidence.measured
        and bool(evidence.environment.strip())
        and bool(evidence.provenance.strip())
    )
