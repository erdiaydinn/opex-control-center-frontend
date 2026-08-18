"""Real-device acceptance for Jarvis local Turkish voice.

The suite separates repository/local-model evidence from actual microphone,
speaker and room performance. It measures wake false-accept/miss behavior,
Turkish recognition, conversational turns, barge-in latency, ASR/TTS latency,
privacy leakage and paid-frontier leakage. Voice biometrics are not part of the
acceptance path; identity remains trusted OIDC/OS-session evidence.
"""

from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .spatial_device_acceptance import DeviceEvidenceTier

VOICE_DEVICE_ACCEPTANCE_CONTRACT = "eay-voice-device-acceptance-v1"


class VoiceDeviceScenario(str, Enum):
    QUIET_NEAR_FIELD = "quiet_near_field"
    NOISY_NEAR_FIELD = "noisy_near_field"
    FAR_FIELD = "far_field"
    TURKISH_PROPER_NOUNS = "turkish_proper_nouns"
    WAKE_NEGATIVE = "wake_negative"
    CONVERSATION_FOLLOWUP = "conversation_followup"
    BARGE_IN = "barge_in"
    DEVICE_REOPEN = "device_reopen"


_REQUIRED_SCENARIOS = frozenset(VoiceDeviceScenario)


class VoiceDeviceProfile(BaseModel):
    profile_ref: str = Field(min_length=1)
    os_build_ref: str = Field(min_length=1)
    machine_ref: str = Field(min_length=1)
    microphone_ref: str = Field(min_length=1)
    speaker_ref: str = Field(min_length=1)
    asr_model_ref: str = Field(min_length=1)
    tts_model_ref: str = Field(min_length=1)
    language_code: str = Field(pattern=r"^[a-z]{2,3}$")
    acoustic_environment_ref: str = Field(min_length=1)
    device_evidence_refs: tuple[str, ...] = Field(min_length=1)
    raw_device_identifiers_retained: bool = False

    @model_validator(mode="after")
    def profile_is_opaque(self) -> "VoiceDeviceProfile":
        if self.raw_device_identifiers_retained:
            raise ValueError("voice_device_profile_cannot_retain_raw_identifiers")
        return self

    @property
    def environment_fingerprint(self) -> str:
        payload = "|".join(
            (
                self.os_build_ref,
                self.machine_ref,
                self.microphone_ref,
                self.speaker_ref,
                self.asr_model_ref,
                self.tts_model_ref,
                self.language_code,
                self.acoustic_environment_ref,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class VoiceDeviceAcceptanceCase(BaseModel):
    case_id: str = Field(min_length=1)
    scenario: VoiceDeviceScenario
    evidence_tier: DeviceEvidenceTier
    environment_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    wake_expected: bool
    wake_detected: bool
    command_expected: bool
    command_eligible: bool
    transcript_semantically_correct: bool
    response_audio_completed: bool
    trusted_identity_valid: bool
    asr_latency_ms: int = Field(ge=0)
    tts_first_audio_latency_ms: int = Field(ge=0)
    barge_in_stop_latency_ms: int | None = Field(default=None, ge=0)
    paid_frontier_calls: int = Field(default=0, ge=0)
    raw_audio_leakage: bool = False
    transcript_leakage: bool = False
    biometric_voice_identity_used: bool = False
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class VoiceDeviceAcceptanceRun(BaseModel):
    contract: str = VOICE_DEVICE_ACCEPTANCE_CONTRACT
    system_ref: str = Field(min_length=1)
    profile: VoiceDeviceProfile
    evidence_tier: DeviceEvidenceTier
    cases: tuple[VoiceDeviceAcceptanceCase, ...] = Field(min_length=1)
    independent_observer_ref: str = Field(min_length=1)
    repository_ci_only: bool = False

    @model_validator(mode="after")
    def run_is_environment_consistent(self) -> "VoiceDeviceAcceptanceRun":
        if any(item.evidence_tier is not self.evidence_tier for item in self.cases):
            raise ValueError("voice_device_acceptance_mixed_evidence_tier")
        if any(item.environment_fingerprint != self.profile.environment_fingerprint for item in self.cases):
            raise ValueError("voice_device_acceptance_environment_mismatch")
        if self.evidence_tier is not DeviceEvidenceTier.SYNTHETIC and self.repository_ci_only:
            raise ValueError("voice_device_acceptance_real_tier_cannot_be_repository_only")
        return self


class VoiceDeviceMetrics(BaseModel):
    wake_false_accept_rate: float = Field(ge=0.0, le=1.0)
    wake_miss_rate: float = Field(ge=0.0, le=1.0)
    command_accuracy: float = Field(ge=0.0, le=1.0)
    semantic_transcript_accuracy: float = Field(ge=0.0, le=1.0)
    p95_asr_latency_ms: int = Field(ge=0)
    p95_tts_first_audio_latency_ms: int = Field(ge=0)
    p95_barge_in_latency_ms: int = Field(ge=0)
    paid_frontier_calls: int = Field(ge=0)
    leakage_events: int = Field(ge=0)


class VoiceDeviceAcceptanceDecision(BaseModel):
    contract: str = VOICE_DEVICE_ACCEPTANCE_CONTRACT
    metrics: VoiceDeviceMetrics
    device_lab_accepted: bool = False
    controlled_field_accepted: bool = False
    production_claim_allowed: bool = False
    covered_scenarios: frozenset[VoiceDeviceScenario]
    blockers: tuple[str, ...] = ()
    automatic_production_promotion_allowed: bool = False

    @model_validator(mode="after")
    def decision_never_auto_promotes(self) -> "VoiceDeviceAcceptanceDecision":
        if self.automatic_production_promotion_allowed:
            raise ValueError("voice_device_acceptance_never_auto_promotes")
        if self.production_claim_allowed and not self.controlled_field_accepted:
            raise ValueError("voice_device_acceptance_production_claim_requires_field")
        return self


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
    return ordered[index]


def evaluate_voice_device_acceptance(run: VoiceDeviceAcceptanceRun) -> VoiceDeviceAcceptanceDecision:
    blockers: list[str] = []
    covered = frozenset(item.scenario for item in run.cases)
    if _REQUIRED_SCENARIOS - covered:
        blockers.append("voice_device_acceptance_required_scenarios_missing")
    if len(run.cases) < 40:
        blockers.append("voice_device_acceptance_minimum_case_count_not_met")

    wake_positive = [item for item in run.cases if item.wake_expected]
    wake_negative = [item for item in run.cases if not item.wake_expected]
    false_accept = sum(item.wake_detected for item in wake_negative)
    missed = sum(not item.wake_detected for item in wake_positive)
    command_cases = [item for item in run.cases if item.command_expected]
    command_correct = sum(item.command_eligible and item.trusted_identity_valid for item in command_cases)
    semantic_correct = sum(item.transcript_semantically_correct for item in command_cases)
    barge_cases = [
        item.barge_in_stop_latency_ms
        for item in run.cases
        if item.scenario is VoiceDeviceScenario.BARGE_IN and item.barge_in_stop_latency_ms is not None
    ]

    metrics = VoiceDeviceMetrics(
        wake_false_accept_rate=round(_rate(false_accept, len(wake_negative)), 6),
        wake_miss_rate=round(_rate(missed, len(wake_positive)), 6),
        command_accuracy=round(_rate(command_correct, len(command_cases)), 6),
        semantic_transcript_accuracy=round(_rate(semantic_correct, len(command_cases)), 6),
        p95_asr_latency_ms=_p95([item.asr_latency_ms for item in run.cases]),
        p95_tts_first_audio_latency_ms=_p95([item.tts_first_audio_latency_ms for item in run.cases]),
        p95_barge_in_latency_ms=_p95([value for value in barge_cases if value is not None]),
        paid_frontier_calls=sum(item.paid_frontier_calls for item in run.cases),
        leakage_events=sum(
            item.raw_audio_leakage or item.transcript_leakage for item in run.cases
        ),
    )

    if metrics.wake_false_accept_rate > 0.01:
        blockers.append("voice_device_acceptance_wake_false_accept_above_floor")
    if metrics.wake_miss_rate > 0.05:
        blockers.append("voice_device_acceptance_wake_miss_above_floor")
    if metrics.command_accuracy < 0.98:
        blockers.append("voice_device_acceptance_command_accuracy_below_floor")
    if metrics.semantic_transcript_accuracy < 0.95:
        blockers.append("voice_device_acceptance_transcript_accuracy_below_floor")
    if metrics.p95_asr_latency_ms > 1000:
        blockers.append("voice_device_acceptance_asr_latency_above_floor")
    if metrics.p95_tts_first_audio_latency_ms > 700:
        blockers.append("voice_device_acceptance_tts_latency_above_floor")
    if not barge_cases or metrics.p95_barge_in_latency_ms > 250:
        blockers.append("voice_device_acceptance_barge_in_latency_above_floor")
    if metrics.paid_frontier_calls:
        blockers.append("voice_device_acceptance_paid_frontier_call_detected")
    if metrics.leakage_events:
        blockers.append("voice_device_acceptance_content_leakage")
    if any(item.biometric_voice_identity_used for item in run.cases):
        blockers.append("voice_device_acceptance_voice_biometric_identity_forbidden")
    if any(item.command_eligible and not item.trusted_identity_valid for item in run.cases):
        blockers.append("voice_device_acceptance_untrusted_identity_command")
    if any(item.command_expected and not item.response_audio_completed for item in run.cases):
        blockers.append("voice_device_acceptance_response_audio_incomplete")
    if run.evidence_tier is DeviceEvidenceTier.SYNTHETIC:
        blockers.append("voice_device_acceptance_real_device_evidence_required")

    lab = not blockers and run.evidence_tier in {
        DeviceEvidenceTier.DEVICE_LAB,
        DeviceEvidenceTier.CONTROLLED_FIELD,
    }
    field = not blockers and run.evidence_tier is DeviceEvidenceTier.CONTROLLED_FIELD
    return VoiceDeviceAcceptanceDecision(
        metrics=metrics,
        device_lab_accepted=lab,
        controlled_field_accepted=field,
        production_claim_allowed=field,
        covered_scenarios=covered,
        blockers=tuple(dict.fromkeys(blockers)),
    )
