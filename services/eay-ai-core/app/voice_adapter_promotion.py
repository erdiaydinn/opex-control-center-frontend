from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .language_capability import LanguageCapability
from .license_gate import assert_model_license_allowed
from .voice_runtime import VoiceAdapterSpec, VoiceProfile


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_sha256(value: str | None) -> bool:
    return bool(value) and len(value or "") == 64 and all(ch in "0123456789abcdef" for ch in value or "")


@dataclass(frozen=True)
class VoiceAdapterPromotion:
    adapter_id: str
    kind: str
    adapter_artifact_sha256: str
    adapter_fingerprint: str
    profile_fingerprint: str
    language_capability_fingerprints: tuple[str, ...]
    reviewer: str
    approval_reference: str
    promoted_at: str
    fingerprint: str


def adapter_fingerprint(adapter: VoiceAdapterSpec) -> str:
    adapter.validate()
    if not adapter.local:
        raise ValueError("voice_adapter_local_required")
    if adapter.kind in {"wakeword", "vad", "stt", "tts"} and not adapter.streaming:
        raise ValueError("voice_adapter_streaming_required")
    if not _is_sha256(adapter.artifact_sha256):
        raise ValueError("voice_adapter_artifact_sha256_required")

    # Runtime code and downloaded model/voice artifacts are separate licensing
    # surfaces. A permissive engine must never implicitly bless restrictive weights.
    assert_model_license_allowed(adapter.resolved_runtime_license_id)
    assert_model_license_allowed(adapter.resolved_artifact_license_id)
    return _sha256(
        {
            "adapter_id": adapter.adapter_id,
            "kind": adapter.kind,
            "implementation": adapter.implementation,
            "local": adapter.local,
            "streaming": adapter.streaming,
            "legacy_license_id": adapter.license_id.strip().lower(),
            "runtime_license_id": adapter.resolved_runtime_license_id,
            "artifact_license_id": adapter.resolved_artifact_license_id,
            "languages": sorted(adapter.languages),
            "artifact_sha256": adapter.artifact_sha256,
        }
    )


class VoiceAdapterPromotionRegistry:
    """Human-gated immutable registry for executable local voice adapters.

    Contract-only adapter targets in ``default_jarvis_profile`` are deliberately not
    executable. A deployment must pin exact model/binary bytes, allow-listed runtime
    and artifact licenses, and approved language capabilities before promotion.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS voice_adapter_promotions (
                adapter_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                adapter_artifact_sha256 TEXT NOT NULL,
                adapter_fingerprint TEXT NOT NULL,
                profile_fingerprint TEXT NOT NULL,
                language_capability_fingerprints_json TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                promoted_at TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE
                )"""
            )

    def promote(
        self,
        *,
        adapter: VoiceAdapterSpec,
        profile: VoiceProfile,
        capabilities: Iterable[LanguageCapability],
        reviewer: str,
        approval_reference: str,
        promoted_at: datetime | None = None,
    ) -> VoiceAdapterPromotion:
        profile.validate()
        if adapter.adapter_id not in {item.adapter_id for item in profile.adapters}:
            raise ValueError("voice_adapter_not_in_profile")
        if profile.clone_reference_voice:
            raise ValueError("voice_reference_clone_forbidden")
        adapter_fp = adapter_fingerprint(adapter)

        by_language = {item.language.split("-", 1)[0]: item for item in capabilities}
        required = {lang.split("-", 1)[0] for lang in adapter.languages}
        missing = sorted(required - set(by_language))
        if missing:
            raise ValueError(f"voice_adapter_language_capability_missing:{','.join(missing)}")
        ineligible = sorted(lang for lang in required if not by_language[lang].production_eligible)
        if ineligible:
            raise ValueError(f"voice_adapter_language_capability_ineligible:{','.join(ineligible)}")

        reviewer = reviewer.strip()
        approval_reference = approval_reference.strip()
        if len(reviewer) < 2:
            raise ValueError("voice_adapter_reviewer_required")
        if len(approval_reference) < 3:
            raise ValueError("voice_adapter_approval_reference_required")

        language_fps = tuple(sorted(by_language[lang].capability_sha256 for lang in required))
        when = promoted_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        payload = {
            "adapter_id": adapter.adapter_id,
            "kind": adapter.kind,
            "adapter_artifact_sha256": adapter.artifact_sha256,
            "adapter_fingerprint": adapter_fp,
            "profile_fingerprint": profile.fingerprint,
            "language_capability_fingerprints": language_fps,
            "reviewer": reviewer,
            "approval_reference": approval_reference,
            "promoted_at": when.isoformat(),
        }
        fingerprint = _sha256(payload)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """INSERT INTO voice_adapter_promotions(
                    adapter_id,kind,adapter_artifact_sha256,adapter_fingerprint,
                    profile_fingerprint,language_capability_fingerprints_json,
                    reviewer,approval_reference,promoted_at,fingerprint
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        adapter.adapter_id,
                        adapter.kind,
                        adapter.artifact_sha256,
                        adapter_fp,
                        profile.fingerprint,
                        json.dumps(language_fps),
                        reviewer,
                        approval_reference,
                        when.isoformat(),
                        fingerprint,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("voice_adapter_promotion_already_exists") from exc
        return self.verify(
            adapter=adapter,
            profile=profile,
            capabilities=capabilities,
        )

    def verify(
        self,
        *,
        adapter: VoiceAdapterSpec,
        profile: VoiceProfile,
        capabilities: Iterable[LanguageCapability],
    ) -> VoiceAdapterPromotion:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM voice_adapter_promotions WHERE adapter_id=?",
                (adapter.adapter_id,),
            ).fetchone()
        if row is None:
            raise KeyError("voice_adapter_promotion_not_found")

        adapter_fp = adapter_fingerprint(adapter)
        if adapter_fp != row["adapter_fingerprint"] or adapter.artifact_sha256 != row["adapter_artifact_sha256"]:
            raise ValueError("voice_adapter_artifact_or_contract_drift")
        if profile.fingerprint != row["profile_fingerprint"]:
            raise ValueError("voice_adapter_profile_drift")

        by_language = {item.language.split("-", 1)[0]: item for item in capabilities}
        required = {lang.split("-", 1)[0] for lang in adapter.languages}
        if required - set(by_language):
            raise ValueError("voice_adapter_language_capability_missing")
        if any(not by_language[lang].production_eligible for lang in required):
            raise ValueError("voice_adapter_language_capability_ineligible")
        expected_language_fps = tuple(sorted(by_language[lang].capability_sha256 for lang in required))
        stored_language_fps = tuple(json.loads(row["language_capability_fingerprints_json"]))
        if expected_language_fps != stored_language_fps:
            raise ValueError("voice_adapter_language_capability_drift")

        payload = {
            "adapter_id": row["adapter_id"],
            "kind": row["kind"],
            "adapter_artifact_sha256": row["adapter_artifact_sha256"],
            "adapter_fingerprint": row["adapter_fingerprint"],
            "profile_fingerprint": row["profile_fingerprint"],
            "language_capability_fingerprints": stored_language_fps,
            "reviewer": row["reviewer"],
            "approval_reference": row["approval_reference"],
            "promoted_at": row["promoted_at"],
        }
        if _sha256(payload) != row["fingerprint"]:
            raise ValueError("voice_adapter_promotion_fingerprint_drift")
        return VoiceAdapterPromotion(
            adapter_id=row["adapter_id"],
            kind=row["kind"],
            adapter_artifact_sha256=row["adapter_artifact_sha256"],
            adapter_fingerprint=row["adapter_fingerprint"],
            profile_fingerprint=row["profile_fingerprint"],
            language_capability_fingerprints=stored_language_fps,
            reviewer=row["reviewer"],
            approval_reference=row["approval_reference"],
            promoted_at=row["promoted_at"],
            fingerprint=row["fingerprint"],
        )
