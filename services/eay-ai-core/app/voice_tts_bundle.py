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
from .voice_adapter_promotion import VoiceAdapterPromotionRegistry
from .voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec, VoiceProfile


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceTtsLanguageArtifact:
    language: str
    voice_id: str
    model_sha256: str
    config_sha256: str
    tokens_sha256: str
    model_card_sha256: str
    artifact_license_id: str
    model_card_source: str

    def validate(self) -> None:
        language = self.language.strip().lower().split("-", 1)[0].split("_", 1)[0]
        if language not in CORE_LANGUAGES:
            raise ValueError("voice_tts_bundle_language_not_enabled")
        if len(self.voice_id.strip()) < 3:
            raise ValueError("voice_tts_bundle_voice_id_required")
        if not self.model_card_source.startswith("https://"):
            raise ValueError("voice_tts_bundle_model_card_source_required")
        for value, code in (
            (self.model_sha256, "voice_tts_bundle_model_hash_invalid"),
            (self.config_sha256, "voice_tts_bundle_config_hash_invalid"),
            (self.tokens_sha256, "voice_tts_bundle_tokens_hash_invalid"),
            (self.model_card_sha256, "voice_tts_bundle_model_card_hash_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)
        assert_model_license_allowed(self.artifact_license_id)

    @property
    def base_language(self) -> str:
        return self.language.strip().lower().split("-", 1)[0].split("_", 1)[0]

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _sha256(
            {
                "language": self.language.strip().lower(),
                "base_language": self.base_language,
                "voice_id": self.voice_id.strip(),
                "model_sha256": self.model_sha256,
                "config_sha256": self.config_sha256,
                "tokens_sha256": self.tokens_sha256,
                "model_card_sha256": self.model_card_sha256,
                "artifact_license_id": self.artifact_license_id.strip().lower(),
                "model_card_source": self.model_card_source,
            }
        )


@dataclass(frozen=True)
class VoiceTtsArtifactBundle:
    bundle_id: str
    bundle_version: str
    runtime_adapter_id: str
    voice_identity_id: str
    phonemizer_data_manifest_fingerprint: str
    phonemizer_license_id: str
    phonemizer_source: str
    artifacts: tuple[VoiceTtsLanguageArtifact, ...]

    def validate(self) -> None:
        if len(self.bundle_id.strip()) < 3 or len(self.bundle_version.strip()) < 1:
            raise ValueError("voice_tts_bundle_identity_required")
        if len(self.runtime_adapter_id.strip()) < 3:
            raise ValueError("voice_tts_bundle_runtime_adapter_required")
        if len(self.voice_identity_id.strip()) < 3:
            raise ValueError("voice_tts_bundle_voice_identity_required")
        if not _valid_sha256(self.phonemizer_data_manifest_fingerprint):
            raise ValueError("voice_tts_bundle_phonemizer_manifest_invalid")
        if not self.phonemizer_source.startswith("https://"):
            raise ValueError("voice_tts_bundle_phonemizer_source_required")
        assert_model_license_allowed(self.phonemizer_license_id)
        if not self.artifacts:
            raise ValueError("voice_tts_bundle_artifacts_required")
        for artifact in self.artifacts:
            artifact.validate()
        by_language = {artifact.base_language: artifact for artifact in self.artifacts}
        if len(by_language) != len(self.artifacts):
            raise ValueError("voice_tts_bundle_duplicate_language")
        missing = sorted(set(CORE_LANGUAGES) - set(by_language))
        extra = sorted(set(by_language) - set(CORE_LANGUAGES))
        if missing or extra:
            raise ValueError("voice_tts_bundle_core_language_coverage_required")
        voice_ids = [artifact.voice_id.strip() for artifact in self.artifacts]
        if len(set(voice_ids)) != len(voice_ids):
            raise ValueError("voice_tts_bundle_duplicate_voice_id")

    @property
    def fingerprint(self) -> str:
        self.validate()
        ordered = sorted(self.artifacts, key=lambda item: item.base_language)
        return _sha256(
            {
                "bundle_id": self.bundle_id.strip(),
                "bundle_version": self.bundle_version.strip(),
                "runtime_adapter_id": self.runtime_adapter_id.strip(),
                "voice_identity_id": self.voice_identity_id.strip(),
                "phonemizer_data_manifest_fingerprint": self.phonemizer_data_manifest_fingerprint,
                "phonemizer_license_id": self.phonemizer_license_id.strip().lower(),
                "phonemizer_source": self.phonemizer_source,
                "artifacts": [
                    {"language": item.language.strip().lower(), "fingerprint": item.fingerprint}
                    for item in ordered
                ],
            }
        )

    def artifact_for(self, language: str) -> VoiceTtsLanguageArtifact:
        base = language.strip().lower().split("-", 1)[0].split("_", 1)[0]
        for artifact in self.artifacts:
            if artifact.base_language == base:
                return artifact
        raise KeyError("voice_tts_bundle_language_artifact_not_found")


@dataclass(frozen=True)
class VoiceTtsBundlePromotion:
    bundle_fingerprint: str
    runtime_adapter_id: str
    runtime_adapter_promotion_fingerprint: str
    profile_fingerprint: str
    language_capability_fingerprints: tuple[str, ...]
    reviewer: str
    approval_reference: str
    promoted_at: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceTtsLanguageExecutionIdentity:
    language: str
    voice_id_sha256: str
    model_sha256: str
    config_sha256: str
    tokens_sha256: str
    model_card_sha256: str
    artifact_license_id_sha256: str
    artifact_fingerprint: str
    fingerprint: str

    def validate(self) -> None:
        if self.language not in CORE_LANGUAGES:
            raise ValueError("voice_tts_execution_language_invalid")
        for value, code in (
            (self.voice_id_sha256, "voice_tts_execution_voice_id_hash_invalid"),
            (self.model_sha256, "voice_tts_execution_model_hash_invalid"),
            (self.config_sha256, "voice_tts_execution_config_hash_invalid"),
            (self.tokens_sha256, "voice_tts_execution_tokens_hash_invalid"),
            (self.model_card_sha256, "voice_tts_execution_model_card_hash_invalid"),
            (self.artifact_license_id_sha256, "voice_tts_execution_license_hash_invalid"),
            (self.artifact_fingerprint, "voice_tts_execution_artifact_fingerprint_invalid"),
            (self.fingerprint, "voice_tts_execution_language_fingerprint_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)


@dataclass(frozen=True)
class VoiceTtsBundleExecutionIdentity:
    bundle_fingerprint: str
    bundle_promotion_fingerprint: str
    runtime_adapter_id: str
    runtime_adapter_promotion_fingerprint: str
    profile_fingerprint: str
    phonemizer_data_manifest_fingerprint: str
    phonemizer_license_id_sha256: str
    phonemizer_source_sha256: str
    language_artifacts: tuple[VoiceTtsLanguageExecutionIdentity, ...]
    fingerprint: str

    def validate(self) -> None:
        for value, code in (
            (self.bundle_fingerprint, "voice_tts_execution_bundle_fingerprint_invalid"),
            (self.bundle_promotion_fingerprint, "voice_tts_execution_bundle_promotion_invalid"),
            (self.runtime_adapter_promotion_fingerprint, "voice_tts_execution_runtime_promotion_invalid"),
            (self.profile_fingerprint, "voice_tts_execution_profile_fingerprint_invalid"),
            (self.phonemizer_data_manifest_fingerprint, "voice_tts_execution_phonemizer_manifest_invalid"),
            (self.phonemizer_license_id_sha256, "voice_tts_execution_phonemizer_license_invalid"),
            (self.phonemizer_source_sha256, "voice_tts_execution_phonemizer_source_invalid"),
            (self.fingerprint, "voice_tts_execution_bundle_identity_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)
        if len(self.runtime_adapter_id.strip()) < 3:
            raise ValueError("voice_tts_execution_runtime_adapter_required")
        for artifact in self.language_artifacts:
            artifact.validate()
        by_language = {artifact.language: artifact for artifact in self.language_artifacts}
        if len(by_language) != len(self.language_artifacts) or set(by_language) != set(CORE_LANGUAGES):
            raise ValueError("voice_tts_execution_core_language_coverage_required")

    def artifact_for(self, language: str) -> VoiceTtsLanguageExecutionIdentity:
        base = language.strip().lower().split("-", 1)[0].split("_", 1)[0]
        for artifact in self.language_artifacts:
            if artifact.language == base:
                return artifact
        raise KeyError("voice_tts_execution_language_artifact_not_found")


def seal_tts_bundle_execution_identity(
    *,
    bundle: VoiceTtsArtifactBundle,
    promotion: VoiceTtsBundlePromotion,
) -> VoiceTtsBundleExecutionIdentity:
    bundle.validate()
    if promotion.bundle_fingerprint != bundle.fingerprint:
        raise ValueError("voice_tts_execution_bundle_promotion_mismatch")
    if promotion.runtime_adapter_id != bundle.runtime_adapter_id:
        raise ValueError("voice_tts_execution_runtime_adapter_mismatch")
    for value, code in (
        (promotion.fingerprint, "voice_tts_execution_bundle_promotion_invalid"),
        (promotion.runtime_adapter_promotion_fingerprint, "voice_tts_execution_runtime_promotion_invalid"),
        (promotion.profile_fingerprint, "voice_tts_execution_profile_fingerprint_invalid"),
    ):
        if not _valid_sha256(value):
            raise ValueError(code)

    language_identities: list[VoiceTtsLanguageExecutionIdentity] = []
    for artifact in sorted(bundle.artifacts, key=lambda item: item.base_language):
        artifact.validate()
        payload = {
            "language": artifact.base_language,
            "voice_id_sha256": hashlib.sha256(artifact.voice_id.strip().encode("utf-8")).hexdigest(),
            "model_sha256": artifact.model_sha256,
            "config_sha256": artifact.config_sha256,
            "tokens_sha256": artifact.tokens_sha256,
            "model_card_sha256": artifact.model_card_sha256,
            "artifact_license_id_sha256": hashlib.sha256(
                artifact.artifact_license_id.strip().lower().encode("utf-8")
            ).hexdigest(),
            "artifact_fingerprint": artifact.fingerprint,
        }
        identity = VoiceTtsLanguageExecutionIdentity(**payload, fingerprint=_sha256(payload))
        identity.validate()
        language_identities.append(identity)

    payload = {
        "bundle_fingerprint": bundle.fingerprint,
        "bundle_promotion_fingerprint": promotion.fingerprint,
        "runtime_adapter_id": bundle.runtime_adapter_id,
        "runtime_adapter_promotion_fingerprint": promotion.runtime_adapter_promotion_fingerprint,
        "profile_fingerprint": promotion.profile_fingerprint,
        "phonemizer_data_manifest_fingerprint": bundle.phonemizer_data_manifest_fingerprint,
        "phonemizer_license_id_sha256": hashlib.sha256(
            bundle.phonemizer_license_id.strip().lower().encode("utf-8")
        ).hexdigest(),
        "phonemizer_source_sha256": hashlib.sha256(bundle.phonemizer_source.encode("utf-8")).hexdigest(),
        "language_artifact_fingerprints": tuple(item.fingerprint for item in language_identities),
    }
    identity = VoiceTtsBundleExecutionIdentity(
        bundle_fingerprint=bundle.fingerprint,
        bundle_promotion_fingerprint=promotion.fingerprint,
        runtime_adapter_id=bundle.runtime_adapter_id,
        runtime_adapter_promotion_fingerprint=promotion.runtime_adapter_promotion_fingerprint,
        profile_fingerprint=promotion.profile_fingerprint,
        phonemizer_data_manifest_fingerprint=bundle.phonemizer_data_manifest_fingerprint,
        phonemizer_license_id_sha256=payload["phonemizer_license_id_sha256"],
        phonemizer_source_sha256=payload["phonemizer_source_sha256"],
        language_artifacts=tuple(language_identities),
        fingerprint=_sha256(payload),
    )
    identity.validate()
    return identity


class VoiceTtsBundlePromotionRegistry:
    """Human-gated promotion for exact per-language TTS voice artifacts and resources.

    The existing TTS adapter promotion remains the runtime/adapter gate. This registry
    adds the voice-weight/resource layer: every core language pins model, config,
    tokens, model-card bytes and artifact license, while the bundle separately pins the
    shared phonemizer resource manifest and its license/source provenance.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS voice_tts_bundle_promotions (
                bundle_fingerprint TEXT PRIMARY KEY,
                runtime_adapter_id TEXT NOT NULL,
                runtime_adapter_promotion_fingerprint TEXT NOT NULL,
                profile_fingerprint TEXT NOT NULL,
                language_capability_fingerprints_json TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                promoted_at TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE
                )"""
            )

    @staticmethod
    def _capability_fingerprints(capabilities: Iterable[LanguageCapability]) -> tuple[str, ...]:
        by_language = {item.language.split("-", 1)[0].split("_", 1)[0]: item for item in capabilities}
        missing = sorted(set(CORE_LANGUAGES) - set(by_language))
        if missing:
            raise ValueError(f"voice_tts_bundle_language_capability_missing:{','.join(missing)}")
        ineligible = sorted(lang for lang in CORE_LANGUAGES if not by_language[lang].production_eligible)
        if ineligible:
            raise ValueError(f"voice_tts_bundle_language_capability_ineligible:{','.join(ineligible)}")
        return tuple(sorted(by_language[lang].capability_sha256 for lang in CORE_LANGUAGES))

    def promote(
        self,
        *,
        bundle: VoiceTtsArtifactBundle,
        runtime_adapter: VoiceAdapterSpec,
        profile: VoiceProfile,
        capabilities: Iterable[LanguageCapability],
        reviewer: str,
        approval_reference: str,
        promoted_at: datetime | None = None,
    ) -> VoiceTtsBundlePromotion:
        bundle.validate()
        profile.validate()
        if runtime_adapter.kind != "tts":
            raise ValueError("voice_tts_bundle_runtime_adapter_kind_invalid")
        if runtime_adapter.adapter_id != bundle.runtime_adapter_id:
            raise ValueError("voice_tts_bundle_runtime_adapter_mismatch")
        if profile.voice_identity_id != bundle.voice_identity_id:
            raise ValueError("voice_tts_bundle_voice_identity_mismatch")
        if runtime_adapter.adapter_id not in {item.adapter_id for item in profile.adapters}:
            raise ValueError("voice_tts_bundle_runtime_adapter_not_in_profile")

        caps = tuple(capabilities)
        adapter_promotion = VoiceAdapterPromotionRegistry(self.db_path).verify(
            adapter=runtime_adapter,
            profile=profile,
            capabilities=caps,
        )
        language_fps = self._capability_fingerprints(caps)
        reviewer = reviewer.strip()
        approval_reference = approval_reference.strip()
        if len(reviewer) < 2:
            raise ValueError("voice_tts_bundle_reviewer_required")
        if len(approval_reference) < 3:
            raise ValueError("voice_tts_bundle_approval_reference_required")
        when = promoted_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        payload = {
            "bundle_fingerprint": bundle.fingerprint,
            "runtime_adapter_id": runtime_adapter.adapter_id,
            "runtime_adapter_promotion_fingerprint": adapter_promotion.fingerprint,
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
                    """INSERT INTO voice_tts_bundle_promotions(
                    bundle_fingerprint,runtime_adapter_id,runtime_adapter_promotion_fingerprint,
                    profile_fingerprint,language_capability_fingerprints_json,reviewer,
                    approval_reference,promoted_at,fingerprint
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        bundle.fingerprint,
                        runtime_adapter.adapter_id,
                        adapter_promotion.fingerprint,
                        profile.fingerprint,
                        json.dumps(language_fps),
                        reviewer,
                        approval_reference,
                        when.isoformat(),
                        fingerprint,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("voice_tts_bundle_promotion_already_exists") from exc
        return self.verify(bundle=bundle, runtime_adapter=runtime_adapter, profile=profile, capabilities=caps)

    def verify(
        self,
        *,
        bundle: VoiceTtsArtifactBundle,
        runtime_adapter: VoiceAdapterSpec,
        profile: VoiceProfile,
        capabilities: Iterable[LanguageCapability],
    ) -> VoiceTtsBundlePromotion:
        bundle.validate()
        caps = tuple(capabilities)
        adapter_promotion = VoiceAdapterPromotionRegistry(self.db_path).verify(
            adapter=runtime_adapter,
            profile=profile,
            capabilities=caps,
        )
        language_fps = self._capability_fingerprints(caps)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM voice_tts_bundle_promotions WHERE bundle_fingerprint=?",
                (bundle.fingerprint,),
            ).fetchone()
        if row is None:
            raise KeyError("voice_tts_bundle_promotion_not_found")
        if row["runtime_adapter_id"] != runtime_adapter.adapter_id:
            raise ValueError("voice_tts_bundle_runtime_adapter_drift")
        if row["runtime_adapter_promotion_fingerprint"] != adapter_promotion.fingerprint:
            raise ValueError("voice_tts_bundle_runtime_promotion_drift")
        if row["profile_fingerprint"] != profile.fingerprint:
            raise ValueError("voice_tts_bundle_profile_drift")
        stored_language_fps = tuple(json.loads(row["language_capability_fingerprints_json"]))
        if stored_language_fps != language_fps:
            raise ValueError("voice_tts_bundle_language_capability_drift")
        payload = {
            "bundle_fingerprint": row["bundle_fingerprint"],
            "runtime_adapter_id": row["runtime_adapter_id"],
            "runtime_adapter_promotion_fingerprint": row["runtime_adapter_promotion_fingerprint"],
            "profile_fingerprint": row["profile_fingerprint"],
            "language_capability_fingerprints": stored_language_fps,
            "reviewer": row["reviewer"],
            "approval_reference": row["approval_reference"],
            "promoted_at": row["promoted_at"],
        }
        if _sha256(payload) != row["fingerprint"]:
            raise ValueError("voice_tts_bundle_promotion_fingerprint_drift")
        return VoiceTtsBundlePromotion(
            bundle_fingerprint=row["bundle_fingerprint"],
            runtime_adapter_id=row["runtime_adapter_id"],
            runtime_adapter_promotion_fingerprint=row["runtime_adapter_promotion_fingerprint"],
            profile_fingerprint=row["profile_fingerprint"],
            language_capability_fingerprints=stored_language_fps,
            reviewer=row["reviewer"],
            approval_reference=row["approval_reference"],
            promoted_at=row["promoted_at"],
            fingerprint=row["fingerprint"],
        )
