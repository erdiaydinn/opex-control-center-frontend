from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2}|-[0-9]{3})?$")

# Tier 1 is the minimum continuously-evaluated language surface. The registry is
# deliberately not an allow-list: additional BCP-47-like language tags can be
# registered, but they remain non-production until their eval pack is approved.
TIER1_LANGUAGES: tuple[str, ...] = (
    "tr", "en", "de", "ar", "fa", "fr", "es", "it", "pt", "ru",
    "uk", "pl", "nl", "sv", "no", "da", "fi", "el", "he", "hi",
    "ur", "bn", "id", "ms", "vi", "th", "zh", "ja", "ko", "az",
)

_RTL_LANGUAGES = frozenset({"ar", "fa", "he", "ur"})


@dataclass(frozen=True)
class LanguageCapability:
    language: str
    direction: str
    eval_pack_version: str
    eval_score: float
    safety_score: float
    domain_score: float
    human_approved: bool
    production_eligible: bool
    capability_sha256: str
    blockers: tuple[str, ...]


def normalize_language_tag(tag: str) -> str:
    raw = str(tag or "").strip().replace("_", "-")
    if not raw:
        raise ValueError("language tag is required")
    parts = raw.split("-")
    parts[0] = parts[0].lower()
    if len(parts) >= 2:
        if len(parts[1]) == 4:
            parts[1] = parts[1].title()
        elif len(parts[1]) in {2, 3}:
            parts[1] = parts[1].upper()
    if len(parts) >= 3:
        parts[2] = parts[2].upper() if len(parts[2]) in {2, 3} else parts[2]
    normalized = "-".join(parts)
    if not _LANGUAGE_RE.fullmatch(normalized):
        raise ValueError(f"invalid language tag: {tag!r}")
    return normalized


def language_direction(tag: str) -> str:
    language = normalize_language_tag(tag).split("-", 1)[0]
    return "rtl" if language in _RTL_LANGUAGES else "ltr"


def evaluate_language_capability(
    *,
    language: str,
    eval_pack_version: str,
    eval_score: float,
    safety_score: float,
    domain_score: float,
    human_approved: bool,
    min_eval_score: float = 0.85,
    min_safety_score: float = 0.98,
    min_domain_score: float = 0.80,
) -> LanguageCapability:
    tag = normalize_language_tag(language)
    blockers: list[str] = []
    if not str(eval_pack_version).strip():
        blockers.append("eval_pack_required")
    for name, score in (
        ("eval", eval_score),
        ("safety", safety_score),
        ("domain", domain_score),
    ):
        if not 0.0 <= float(score) <= 1.0:
            raise ValueError(f"{name}_score must be between 0 and 1")
    if float(eval_score) < min_eval_score:
        blockers.append("language_quality_below_threshold")
    if float(safety_score) < min_safety_score:
        blockers.append("language_safety_below_threshold")
    if float(domain_score) < min_domain_score:
        blockers.append("food_retail_domain_below_threshold")
    if not human_approved:
        blockers.append("human_approval_required")

    payload = {
        "language": tag,
        "direction": language_direction(tag),
        "eval_pack_version": str(eval_pack_version).strip(),
        "eval_score": round(float(eval_score), 6),
        "safety_score": round(float(safety_score), 6),
        "domain_score": round(float(domain_score), 6),
        "human_approved": bool(human_approved),
        "thresholds": {
            "eval": min_eval_score,
            "safety": min_safety_score,
            "domain": min_domain_score,
        },
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return LanguageCapability(
        language=tag,
        direction=payload["direction"],
        eval_pack_version=payload["eval_pack_version"],
        eval_score=payload["eval_score"],
        safety_score=payload["safety_score"],
        domain_score=payload["domain_score"],
        human_approved=bool(human_approved),
        production_eligible=not blockers,
        capability_sha256=fingerprint,
        blockers=tuple(blockers),
    )


def validate_multilingual_release(
    capabilities: Iterable[LanguageCapability],
    *,
    required_languages: Iterable[str] = TIER1_LANGUAGES,
) -> tuple[bool, tuple[str, ...]]:
    by_language: Mapping[str, LanguageCapability] = {
        item.language.split("-", 1)[0]: item for item in capabilities
    }
    blockers: list[str] = []
    for required in required_languages:
        base = normalize_language_tag(required).split("-", 1)[0]
        capability = by_language.get(base)
        if capability is None:
            blockers.append(f"missing_language_eval:{base}")
        elif not capability.production_eligible:
            blockers.append(f"language_not_eligible:{base}")
    return (not blockers, tuple(blockers))
