from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


CORE_LANGUAGES = ("tr", "en", "de", "ar", "fa")
RTL_LANGUAGES = frozenset({"ar", "fa"})


class VoiceState(str, Enum):
    IDLE = "idle"
    WAKE_LISTEN = "wake_listen"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    APPROVAL_REQUIRED = "approval_required"
    ERROR = "error"


ActionRisk = Literal["read", "write", "critical"]
AdapterKind = Literal["wakeword", "vad", "stt", "tts"]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceAdapterSpec:
    adapter_id: str
    kind: AdapterKind
    implementation: str
    local: bool
    streaming: bool
    license_id: str
    languages: tuple[str, ...]
    artifact_sha256: str | None = None
    runtime_license_id: str | None = None
    artifact_license_id: str | None = None

    @property
    def resolved_runtime_license_id(self) -> str:
        return (self.runtime_license_id or self.license_id).strip().lower()

    @property
    def resolved_artifact_license_id(self) -> str:
        return (self.artifact_license_id or self.license_id).strip().lower()

    def validate(self) -> None:
        if not self.adapter_id.strip() or not self.implementation.strip():
            raise ValueError("voice_adapter_identity_required")
        if not self.license_id.strip():
            raise ValueError("voice_adapter_license_required")
        if not self.resolved_runtime_license_id:
            raise ValueError("voice_adapter_runtime_license_required")
        if not self.resolved_artifact_license_id:
            raise ValueError("voice_adapter_artifact_license_required")
        unknown = sorted(set(self.languages) - set(CORE_LANGUAGES))
        if unknown:
            raise ValueError(f"voice_adapter_unknown_language:{','.join(unknown)}")
        if self.artifact_sha256 is not None and (
            len(self.artifact_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.artifact_sha256)
        ):
            raise ValueError("voice_adapter_artifact_sha256_invalid")


@dataclass(frozen=True)
class VoiceProfile:
    profile_id: str
    wake_phrases: tuple[str, ...]
    languages: tuple[str, ...]
    sample_rate_hz: int
    full_duplex: bool
    barge_in: bool
    local_first: bool
    voice_identity_id: str
    clone_reference_voice: bool
    adapters: tuple[VoiceAdapterSpec, ...]

    def validate(self) -> None:
        if self.sample_rate_hz not in {16000, 24000, 48000}:
            raise ValueError("voice_sample_rate_unsupported")
        if not self.local_first:
            raise ValueError("voice_local_first_required")
        if self.clone_reference_voice:
            raise ValueError("voice_reference_clone_forbidden")
        if set(self.languages) != set(CORE_LANGUAGES):
            raise ValueError("voice_core_language_coverage_required")
        if len(set(self.wake_phrases)) != len(self.wake_phrases):
            raise ValueError("voice_duplicate_wake_phrase")
        kinds = {adapter.kind for adapter in self.adapters}
        if kinds != {"wakeword", "vad", "stt", "tts"}:
            raise ValueError("voice_pipeline_adapter_coverage_required")
        for adapter in self.adapters:
            adapter.validate()

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _sha256(
            {
                "profile_id": self.profile_id,
                "wake_phrases": self.wake_phrases,
                "languages": self.languages,
                "sample_rate_hz": self.sample_rate_hz,
                "full_duplex": self.full_duplex,
                "barge_in": self.barge_in,
                "local_first": self.local_first,
                "voice_identity_id": self.voice_identity_id,
                "clone_reference_voice": self.clone_reference_voice,
                "adapters": [adapter.__dict__ for adapter in self.adapters],
            }
        )


@dataclass(frozen=True)
class VoiceTurnContext:
    session_id: str
    language: str
    state: VoiceState
    conversation_id: str | None = None
    active_tool_call_id: str | None = None
    pending_action_risk: ActionRisk | None = None
    approval_reference: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def rtl(self) -> bool:
        return self.language in RTL_LANGUAGES


class VoiceStateMachine:
    """Deterministic full-duplex session state machine.

    It intentionally contains no microphone, model or TTS implementation. Runtime
    adapters remain replaceable and local-first; this object only governs safe turn
    transitions, barge-in, and approval boundaries.
    """

    def __init__(self, *, barge_in: bool = True):
        self.state = VoiceState.IDLE
        self.barge_in = barge_in

    def wake(self) -> VoiceState:
        if self.state not in {VoiceState.IDLE, VoiceState.WAKE_LISTEN}:
            raise ValueError("voice_wake_invalid_state")
        self.state = VoiceState.LISTENING
        return self.state

    def end_utterance(self) -> VoiceState:
        if self.state != VoiceState.LISTENING:
            raise ValueError("voice_end_utterance_invalid_state")
        self.state = VoiceState.THINKING
        return self.state

    def begin_speaking(self) -> VoiceState:
        if self.state != VoiceState.THINKING:
            raise ValueError("voice_speak_invalid_state")
        self.state = VoiceState.SPEAKING
        return self.state

    def interrupt(self) -> VoiceState:
        if self.state != VoiceState.SPEAKING or not self.barge_in:
            raise ValueError("voice_interrupt_not_allowed")
        self.state = VoiceState.INTERRUPTED
        return self.state

    def resume_listening(self) -> VoiceState:
        if self.state not in {VoiceState.INTERRUPTED, VoiceState.SPEAKING}:
            raise ValueError("voice_resume_invalid_state")
        self.state = VoiceState.LISTENING
        return self.state

    def require_action_approval(self, risk: ActionRisk, approval_reference: str | None = None) -> VoiceState:
        if risk == "read":
            return self.state
        if approval_reference and approval_reference.strip():
            return self.state
        self.state = VoiceState.APPROVAL_REQUIRED
        return self.state

    def approve(self, approval_reference: str) -> VoiceState:
        if self.state != VoiceState.APPROVAL_REQUIRED:
            raise ValueError("voice_approval_invalid_state")
        if len(approval_reference.strip()) < 3:
            raise ValueError("voice_approval_reference_required")
        self.state = VoiceState.THINKING
        return self.state


@dataclass(frozen=True)
class ProactiveSuggestionPolicy:
    """Jarvis-like initiative without autonomous side effects."""

    max_suggestions_per_hour: int = 6
    require_material_signal: bool = True
    allow_read_only_context: bool = True
    allow_write_without_approval: bool = False
    allow_critical_without_approval: bool = False

    def permits(self, *, risk: ActionRisk, material_signal: bool) -> bool:
        if self.require_material_signal and not material_signal:
            return False
        if risk == "read":
            return self.allow_read_only_context
        if risk == "write":
            return self.allow_write_without_approval
        return self.allow_critical_without_approval


def default_jarvis_profile() -> VoiceProfile:
    """Return the dependency-neutral target profile for EAY's voice runtime.

    Implementation names are adapter targets, not bundled dependencies. Deployment
    must independently verify package/model licenses and artifact hashes before use.
    Runtime code and model/voice artifact licenses are deliberately tracked as
    separate contracts because a permissive engine does not imply permissive weights.
    """

    adapters = (
        VoiceAdapterSpec(
            adapter_id="wakeword-local-v1",
            kind="wakeword",
            implementation="openwakeword-compatible",
            local=True,
            streaming=True,
            license_id="deployment-review-required",
            languages=CORE_LANGUAGES,
        ),
        VoiceAdapterSpec(
            adapter_id="vad-local-v1",
            kind="vad",
            implementation="silero-vad-compatible",
            local=True,
            streaming=True,
            license_id="deployment-review-required",
            languages=CORE_LANGUAGES,
        ),
        VoiceAdapterSpec(
            adapter_id="stt-local-v1",
            kind="stt",
            implementation="whisper-compatible",
            local=True,
            streaming=True,
            license_id="deployment-review-required",
            languages=CORE_LANGUAGES,
        ),
        VoiceAdapterSpec(
            adapter_id="tts-local-v1",
            kind="tts",
            implementation="multilingual-local-tts",
            local=True,
            streaming=True,
            license_id="deployment-review-required",
            languages=CORE_LANGUAGES,
        ),
    )
    profile = VoiceProfile(
        profile_id="eay-jarvis-v1",
        wake_phrases=("EAY", "Hey EAY", "Jarvis"),
        languages=CORE_LANGUAGES,
        sample_rate_hz=16000,
        full_duplex=True,
        barge_in=True,
        local_first=True,
        voice_identity_id="eay-natural-neutral-v1",
        clone_reference_voice=False,
        adapters=adapters,
    )
    profile.validate()
    return profile
