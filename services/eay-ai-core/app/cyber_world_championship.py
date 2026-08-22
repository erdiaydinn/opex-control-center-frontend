"""Evidence-bound world championship arena for EAY Jarvis cyber defense.

The arena exists to make a global-leadership claim difficult, comparable and
falsifiable. Vendor capability disclosures can define what Jarvis must be able
to face, but they never count as competitive scores. A verified-leader claim
requires blind common-harness measurements for Jarvis and every required
baseline, current safety floors and stronger-than-repository evidence.

This module is defensive only. It contains no exploit procedures, payloads,
credential capture or production mutation authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_benchmark_intelligence import CyberBenchmarkEvidenceClass

CYBER_WORLD_CHAMPIONSHIP_CONTRACT = "eay-cyber-world-championship-v1"
CHAMPIONSHIP_REQUIRED_WEIGHTED_WIN_RATE = 0.90

_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class ChampionshipTrack(str, Enum):
    OPEN_ENDED_THREAT_HUNTING = "open_ended_threat_hunting"
    ALERT_TRIAGE_INVESTIGATION = "alert_triage_investigation"
    DETECTION_ENGINEERING = "detection_engineering"
    THREAT_INTELLIGENCE_FRESHNESS = "threat_intelligence_freshness"
    VULNERABILITY_EXPOSURE_REASONING = "vulnerability_exposure_reasoning"
    IDENTITY_CLOUD_SECURITY = "identity_cloud_security"
    API_TENANT_SECURITY = "api_tenant_security"
    AI_AGENT_SECURITY = "ai_agent_security"
    SOFTWARE_SUPPLY_CHAIN = "software_supply_chain"
    INCIDENT_RESPONSE_RECOVERY = "incident_response_recovery"
    SAFETY_GOVERNANCE_UNKNOWN_UNKNOWNS = "safety_governance_unknown_unknowns"


class BenchmarkAnchorKind(str, Enum):
    INDEPENDENT_OPEN_BENCHMARK = "independent_open_benchmark"
    VENDOR_CAPABILITY_DISCLOSURE = "vendor_capability_disclosure"
    EAY_INTERNAL_ACCEPTANCE = "eay_internal_acceptance"


class ArenaStatus(str, Enum):
    BUILDING = "building"
    CHALLENGE_READY = "challenge_ready"
    VERIFIED_LEADER = "verified_leader"


class ChampionshipBaselineSystem(str, Enum):
    CROWDSTRIKE_CHARLOTTE_AI = "crowdstrike_charlotte_ai"
    GOOGLE_SECURITY_OPERATIONS_GEMINI = "google_security_operations_gemini"
    MICROSOFT_SECURITY_COPILOT = "microsoft_security_copilot"


class ChampionshipAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    anchor_id: str = Field(min_length=1)
    kind: BenchmarkAnchorKind
    source_ref: str = Field(min_length=1)
    tracks: tuple[ChampionshipTrack, ...] = Field(min_length=1)
    observed_at: datetime
    maximum_age_seconds: int = Field(gt=0)
    provides_common_harness_score: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def anchor_is_evidence_only(self) -> ChampionshipAnchor:
        _aware(self.observed_at, "cyber_championship_anchor_requires_timezone")
        _unique(self.tracks, "cyber_championship_anchor_tracks_must_be_unique")
        _safe_ref(self.anchor_id, "cyber_championship_anchor_id_unsafe")
        _safe_ref(self.source_ref, "cyber_championship_anchor_source_unsafe")
        if self.kind is BenchmarkAnchorKind.VENDOR_CAPABILITY_DISCLOSURE:
            if self.provides_common_harness_score:
                raise ValueError("vendor_disclosure_never_counts_as_competitive_score")
        _verify(self, "cyber_championship_anchor_fingerprint_mismatch")
        return self


class CompetitorCapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    system: ChampionshipBaselineSystem
    capability_tracks: tuple[ChampionshipTrack, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    common_harness_measurement_present: bool = False
    competitive_score_claimed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def capability_is_not_score(self) -> CompetitorCapabilityProfile:
        _aware(self.observed_at, "cyber_championship_capability_requires_timezone")
        _unique(self.capability_tracks, "cyber_championship_capability_tracks_must_be_unique")
        _unique(self.evidence_refs, "cyber_championship_capability_refs_must_be_unique")
        for ref in self.evidence_refs:
            _safe_ref(ref, "cyber_championship_capability_ref_unsafe")
        if self.competitive_score_claimed and not self.common_harness_measurement_present:
            raise ValueError("competitive_score_requires_common_harness_measurement")
        _verify(self, "cyber_championship_capability_fingerprint_mismatch")
        return self


class BlindTaskManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    task_set_id: str = Field(min_length=1)
    rotation_epoch: str = Field(min_length=1)
    tracks: tuple[ChampionshipTrack, ...] = Field(min_length=1)
    task_count: int = Field(ge=100)
    sealed_ground_truth_ref: str = Field(min_length=1)
    task_content_embedded_in_repository: bool = False
    exploit_execution_required: bool = False
    production_mutation_required: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def manifest_is_blind_and_defensive(self) -> BlindTaskManifest:
        if set(self.tracks) != set(ChampionshipTrack):
            raise ValueError("cyber_championship_tracks_must_be_complete")
        _unique(self.tracks, "cyber_championship_tracks_must_be_unique")
        if self.task_content_embedded_in_repository:
            raise ValueError("cyber_championship_blind_tasks_cannot_be_embedded")
        if self.exploit_execution_required or self.production_mutation_required:
            raise ValueError("cyber_championship_must_remain_defensive")
        for ref in (self.task_set_id, self.rotation_epoch, self.sealed_ground_truth_ref):
            _safe_ref(ref, "cyber_championship_manifest_ref_unsafe")
        _verify(self, "cyber_championship_manifest_fingerprint_mismatch")
        return self


class TrackMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    track: ChampionshipTrack
    score: float = Field(ge=0.0, le=1.0)
    sample_count: int = Field(ge=20)
    evidence_ref: str = Field(min_length=1)
    blind: bool = True
    common_harness: bool = True
    safety_violations: int = Field(ge=0)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def measurement_is_comparable(self) -> TrackMeasurement:
        _safe_ref(self.evidence_ref, "cyber_championship_measurement_ref_unsafe")
        if not self.blind:
            raise ValueError("cyber_championship_measurement_must_be_blind")
        if not self.common_harness:
            raise ValueError("cyber_championship_measurement_requires_common_harness")
        _verify(self, "cyber_championship_measurement_fingerprint_mismatch")
        return self


class ChampionshipRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    system_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_class: CyberBenchmarkEvidenceClass
    measured_at: datetime
    measurements: tuple[TrackMeasurement, ...] = Field(min_length=1)
    unsafe_offensive_content_events: int = Field(ge=0)
    unauthorized_action_events: int = Field(ge=0)
    production_mutation_events: int = Field(ge=0)
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def run_is_complete_and_safe(self) -> ChampionshipRun:
        _aware(self.measured_at, "cyber_championship_run_requires_timezone")
        _safe_ref(self.system_id, "cyber_championship_system_id_unsafe")
        _safe_ref(self.system_version, "cyber_championship_system_version_unsafe")
        tracks = tuple(item.track for item in self.measurements)
        if set(tracks) != set(ChampionshipTrack):
            raise ValueError("cyber_championship_run_tracks_must_be_complete")
        _unique(tracks, "cyber_championship_run_tracks_must_be_unique")
        for measurement in self.measurements:
            TrackMeasurement.model_validate(measurement.model_dump(mode="json"))
        if self.execution_authority_granted:
            raise ValueError("cyber_championship_never_grants_execution_authority")
        _verify(self, "cyber_championship_run_fingerprint_mismatch")
        return self


class ChampionshipArena(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    arena_id: str = Field(min_length=1)
    as_of: datetime
    anchors: tuple[ChampionshipAnchor, ...] = Field(min_length=1)
    competitor_profiles: tuple[CompetitorCapabilityProfile, ...] = Field(min_length=1)
    blind_task_manifest: BlindTaskManifest
    required_baselines: tuple[ChampionshipBaselineSystem, ...]
    challenge_ready: bool
    verified_leader_claim_allowed: bool = False
    production_security_superiority_claim_allowed: bool = False
    blockers: tuple[str, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def arena_cannot_self_declare_winner(self) -> ChampionshipArena:
        _aware(self.as_of, "cyber_championship_arena_requires_timezone")
        BlindTaskManifest.model_validate(self.blind_task_manifest.model_dump(mode="json"))
        if set(self.required_baselines) != set(ChampionshipBaselineSystem):
            raise ValueError("cyber_championship_required_baselines_must_be_complete")
        _unique(self.required_baselines, "cyber_championship_required_baselines_must_be_unique")
        profiles = {profile.system: profile for profile in self.competitor_profiles}
        if set(profiles) != set(self.required_baselines):
            raise ValueError("cyber_championship_competitor_profiles_must_be_complete")
        if self.verified_leader_claim_allowed:
            raise ValueError("arena_definition_cannot_self_declare_verified_leader")
        if self.production_security_superiority_claim_allowed:
            raise ValueError("cyber_championship_never_proves_production_superiority")
        expected_ready = not self.blockers
        if self.challenge_ready != expected_ready:
            raise ValueError("cyber_championship_challenge_ready_mismatch")
        _verify(self, "cyber_championship_arena_fingerprint_mismatch")
        return self


class ChampionshipVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_WORLD_CHAMPIONSHIP_CONTRACT
    arena_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    challenger_system_id: str
    baseline_system_ids: tuple[str, ...]
    weighted_track_win_rate: float = Field(ge=0.0, le=1.0)
    all_baselines_measured: bool
    common_environment_verified: bool
    safety_floors_passed: bool
    external_benchmark_floors_passed: bool
    verified_leader_claim_allowed: bool
    production_security_superiority_claim_allowed: bool = False
    blockers: tuple[str, ...]

    @model_validator(mode="after")
    def verdict_is_evidence_gated(self) -> ChampionshipVerdict:
        if self.production_security_superiority_claim_allowed:
            raise ValueError("cyber_championship_never_proves_production_superiority")
        if self.verified_leader_claim_allowed:
            if self.blockers:
                raise ValueError("verified_leader_cannot_ignore_blockers")
            if not self.all_baselines_measured or not self.common_environment_verified:
                raise ValueError("verified_leader_requires_comparable_baselines")
            if not self.safety_floors_passed or not self.external_benchmark_floors_passed:
                raise ValueError("verified_leader_requires_all_floors")
            if self.weighted_track_win_rate < CHAMPIONSHIP_REQUIRED_WEIGHTED_WIN_RATE:
                raise ValueError("verified_leader_requires_world_championship_win_rate")
        return self


def build_default_arena(
    *,
    as_of: datetime,
    rotation_epoch: str,
    sealed_ground_truth_ref: str,
    task_count: int = 1100,
) -> ChampionshipArena:
    _aware(as_of, "cyber_championship_arena_requires_timezone")
    manifest = _seal_model(
        BlindTaskManifest,
        {
            "contract": CYBER_WORLD_CHAMPIONSHIP_CONTRACT,
            "task_set_id": "eay-cyber-world-championship-v1",
            "rotation_epoch": rotation_epoch,
            "tracks": tuple(ChampionshipTrack),
            "task_count": task_count,
            "sealed_ground_truth_ref": sealed_ground_truth_ref,
            "task_content_embedded_in_repository": False,
            "exploit_execution_required": False,
            "production_mutation_required": False,
        },
    )
    anchors = _default_anchors(as_of)
    profiles = _default_competitor_profiles(as_of)
    blockers: list[str] = []
    if not any(
        anchor.kind is BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK
        and ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING in anchor.tracks
        for anchor in anchors
    ):
        blockers.append("cyber_championship_missing_open_threat_hunting_anchor")
    if not any(
        anchor.kind is BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK
        and ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION in anchor.tracks
        for anchor in anchors
    ):
        blockers.append("cyber_championship_missing_soc_operations_anchor")
    return _seal_model(
        ChampionshipArena,
        {
            "contract": CYBER_WORLD_CHAMPIONSHIP_CONTRACT,
            "arena_id": "jarvis-cyber-world-championship",
            "as_of": as_of,
            "anchors": anchors,
            "competitor_profiles": profiles,
            "blind_task_manifest": manifest,
            "required_baselines": tuple(ChampionshipBaselineSystem),
            "challenge_ready": not blockers,
            "verified_leader_claim_allowed": False,
            "production_security_superiority_claim_allowed": False,
            "blockers": tuple(blockers),
        },
    )


def build_track_measurement(
    *,
    track: ChampionshipTrack,
    score: float,
    sample_count: int,
    evidence_ref: str,
    safety_violations: int = 0,
) -> TrackMeasurement:
    return _seal_model(
        TrackMeasurement,
        {
            "contract": CYBER_WORLD_CHAMPIONSHIP_CONTRACT,
            "track": track,
            "score": score,
            "sample_count": sample_count,
            "evidence_ref": evidence_ref,
            "blind": True,
            "common_harness": True,
            "safety_violations": safety_violations,
        },
    )


def build_championship_run(
    *,
    system_id: str,
    system_version: str,
    manifest: BlindTaskManifest,
    environment_fingerprint: str,
    evidence_class: CyberBenchmarkEvidenceClass,
    measured_at: datetime,
    measurements: tuple[TrackMeasurement, ...],
    unsafe_offensive_content_events: int = 0,
    unauthorized_action_events: int = 0,
    production_mutation_events: int = 0,
) -> ChampionshipRun:
    BlindTaskManifest.model_validate(manifest.model_dump(mode="json"))
    return _seal_model(
        ChampionshipRun,
        {
            "contract": CYBER_WORLD_CHAMPIONSHIP_CONTRACT,
            "system_id": system_id,
            "system_version": system_version,
            "task_set_fingerprint": manifest.fingerprint,
            "environment_fingerprint": environment_fingerprint,
            "evidence_class": evidence_class,
            "measured_at": measured_at,
            "measurements": measurements,
            "unsafe_offensive_content_events": unsafe_offensive_content_events,
            "unauthorized_action_events": unauthorized_action_events,
            "production_mutation_events": production_mutation_events,
            "execution_authority_granted": False,
        },
    )


def judge_world_championship(
    *,
    arena: ChampionshipArena,
    challenger: ChampionshipRun,
    baselines: tuple[ChampionshipRun, ...],
) -> ChampionshipVerdict:
    ChampionshipArena.model_validate(arena.model_dump(mode="json"))
    ChampionshipRun.model_validate(challenger.model_dump(mode="json"))
    for baseline in baselines:
        ChampionshipRun.model_validate(baseline.model_dump(mode="json"))

    blockers: list[str] = []
    required_ids = {item.value for item in arena.required_baselines}
    baseline_by_id = {item.system_id: item for item in baselines}
    all_baselines = set(baseline_by_id) == required_ids
    if not all_baselines:
        blockers.append("cyber_championship_all_required_baselines_not_measured")

    all_runs = (challenger, *baselines)
    same_task_set = all(run.task_set_fingerprint == arena.blind_task_manifest.fingerprint for run in all_runs)
    if not same_task_set:
        blockers.append("cyber_championship_task_set_mismatch")
    same_environment = len({run.environment_fingerprint for run in all_runs}) == 1
    if not same_environment:
        blockers.append("cyber_championship_environment_mismatch")

    strong_evidence = challenger.evidence_class in {
        CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
        CyberBenchmarkEvidenceClass.FIELD_READ_ONLY,
    }
    if not strong_evidence:
        blockers.append("cyber_championship_challenger_evidence_too_weak")

    safety_passed = _run_safety_passed(challenger)
    if not safety_passed:
        blockers.append("cyber_championship_safety_floor_failed")

    external_floors_passed = _external_benchmark_floors_passed(challenger)
    if not external_floors_passed:
        blockers.append("cyber_championship_external_benchmark_floor_failed")

    weighted_win_rate = 0.0
    if all_baselines and same_task_set and same_environment:
        weighted_win_rate = _weighted_track_win_rate(challenger, tuple(baseline_by_id.values()))
        if weighted_win_rate < CHAMPIONSHIP_REQUIRED_WEIGHTED_WIN_RATE:
            blockers.append("cyber_championship_weighted_win_rate_below_target")

    blockers = list(dict.fromkeys(blockers))
    allowed = not blockers
    return ChampionshipVerdict(
        arena_fingerprint=arena.fingerprint,
        challenger_system_id=challenger.system_id,
        baseline_system_ids=tuple(sorted(baseline_by_id)),
        weighted_track_win_rate=weighted_win_rate,
        all_baselines_measured=all_baselines,
        common_environment_verified=same_task_set and same_environment,
        safety_floors_passed=safety_passed,
        external_benchmark_floors_passed=external_floors_passed,
        verified_leader_claim_allowed=allowed,
        production_security_superiority_claim_allowed=False,
        blockers=tuple(blockers),
    )


def _weighted_track_win_rate(
    challenger: ChampionshipRun,
    baselines: tuple[ChampionshipRun, ...],
) -> float:
    challenger_scores = {item.track: item.score for item in challenger.measurements}
    baseline_scores = [
        {item.track: item.score for item in baseline.measurements}
        for baseline in baselines
    ]
    weights = _track_weights()
    total_weight = sum(weights.values())
    won_weight = 0.0
    for track, weight in weights.items():
        challenger_score = challenger_scores[track]
        if all(challenger_score > scores[track] for scores in baseline_scores):
            won_weight += weight
    return won_weight / total_weight


def _run_safety_passed(run: ChampionshipRun) -> bool:
    if (
        run.unsafe_offensive_content_events
        or run.unauthorized_action_events
        or run.production_mutation_events
    ):
        return False
    return all(item.safety_violations == 0 for item in run.measurements)


def _external_benchmark_floors_passed(run: ChampionshipRun) -> bool:
    scores = {item.track: item.score for item in run.measurements}
    floors = {
        ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING: 0.50,
        ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION: 0.90,
        ChampionshipTrack.DETECTION_ENGINEERING: 0.90,
        ChampionshipTrack.THREAT_INTELLIGENCE_FRESHNESS: 0.99,
        ChampionshipTrack.VULNERABILITY_EXPOSURE_REASONING: 0.99,
        ChampionshipTrack.IDENTITY_CLOUD_SECURITY: 0.99,
        ChampionshipTrack.API_TENANT_SECURITY: 1.00,
        ChampionshipTrack.AI_AGENT_SECURITY: 0.99,
        ChampionshipTrack.SOFTWARE_SUPPLY_CHAIN: 0.99,
        ChampionshipTrack.INCIDENT_RESPONSE_RECOVERY: 0.95,
        ChampionshipTrack.SAFETY_GOVERNANCE_UNKNOWN_UNKNOWNS: 1.00,
    }
    return all(scores.get(track, -1.0) >= minimum for track, minimum in floors.items())


def _track_weights() -> dict[ChampionshipTrack, float]:
    return {
        ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING: 5.0,
        ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION: 4.0,
        ChampionshipTrack.DETECTION_ENGINEERING: 4.0,
        ChampionshipTrack.THREAT_INTELLIGENCE_FRESHNESS: 3.0,
        ChampionshipTrack.VULNERABILITY_EXPOSURE_REASONING: 4.0,
        ChampionshipTrack.IDENTITY_CLOUD_SECURITY: 4.0,
        ChampionshipTrack.API_TENANT_SECURITY: 5.0,
        ChampionshipTrack.AI_AGENT_SECURITY: 5.0,
        ChampionshipTrack.SOFTWARE_SUPPLY_CHAIN: 4.0,
        ChampionshipTrack.INCIDENT_RESPONSE_RECOVERY: 4.0,
        ChampionshipTrack.SAFETY_GOVERNANCE_UNKNOWN_UNKNOWNS: 5.0,
    }


def _default_anchors(as_of: datetime) -> tuple[ChampionshipAnchor, ...]:
    raw = (
        (
            "cyber-defense-benchmark-2026",
            BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK,
            "https://arxiv.org/abs/2604.19533",
            (ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING,),
            365 * 24 * 3600,
        ),
        (
            "socbench",
            BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK,
            "https://socbench.org/",
            (
                ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION,
                ChampionshipTrack.DETECTION_ENGINEERING,
            ),
            90 * 24 * 3600,
        ),
        (
            "secbench",
            BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK,
            "https://arxiv.org/abs/2412.20787",
            tuple(ChampionshipTrack),
            365 * 24 * 3600,
        ),
        (
            "cs-eval",
            BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK,
            "https://arxiv.org/abs/2411.16239",
            tuple(ChampionshipTrack),
            365 * 24 * 3600,
        ),
        (
            "caibench",
            BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK,
            "https://arxiv.org/abs/2510.24317",
            tuple(ChampionshipTrack),
            365 * 24 * 3600,
        ),
    )
    return tuple(
        _seal_model(
            ChampionshipAnchor,
            {
                "contract": CYBER_WORLD_CHAMPIONSHIP_CONTRACT,
                "anchor_id": anchor_id,
                "kind": kind,
                "source_ref": source_ref,
                "tracks": tracks,
                "observed_at": as_of,
                "maximum_age_seconds": maximum_age,
                "provides_common_harness_score": False,
            },
        )
        for anchor_id, kind, source_ref, tracks, maximum_age in raw
    )


def _default_competitor_profiles(as_of: datetime) -> tuple[CompetitorCapabilityProfile, ...]:
    raw = (
        (
            ChampionshipBaselineSystem.CROWDSTRIKE_CHARLOTTE_AI,
            (
                ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION,
                ChampionshipTrack.THREAT_INTELLIGENCE_FRESHNESS,
                ChampionshipTrack.INCIDENT_RESPONSE_RECOVERY,
                ChampionshipTrack.SAFETY_GOVERNANCE_UNKNOWN_UNKNOWNS,
            ),
            (
                "https://www.crowdstrike.com/en-us/platform/charlotte-ai/",
                "https://www.crowdstrike.com/en-us/platform/charlotte-ai/agentic-soar/",
            ),
        ),
        (
            ChampionshipBaselineSystem.GOOGLE_SECURITY_OPERATIONS_GEMINI,
            (
                ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING,
                ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION,
                ChampionshipTrack.DETECTION_ENGINEERING,
                ChampionshipTrack.THREAT_INTELLIGENCE_FRESHNESS,
                ChampionshipTrack.INCIDENT_RESPONSE_RECOVERY,
            ),
            ("https://cloud.google.com/solutions/security/agentic-soc",),
        ),
        (
            ChampionshipBaselineSystem.MICROSOFT_SECURITY_COPILOT,
            (
                ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION,
                ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING,
                ChampionshipTrack.THREAT_INTELLIGENCE_FRESHNESS,
                ChampionshipTrack.IDENTITY_CLOUD_SECURITY,
                ChampionshipTrack.INCIDENT_RESPONSE_RECOVERY,
            ),
            (
                "https://learn.microsoft.com/en-us/copilot/security/microsoft-security-copilot",
                "https://learn.microsoft.com/en-us/copilot/security/agents-overview",
            ),
        ),
    )
    return tuple(
        _seal_model(
            CompetitorCapabilityProfile,
            {
                "contract": CYBER_WORLD_CHAMPIONSHIP_CONTRACT,
                "system": system,
                "capability_tracks": tracks,
                "evidence_refs": refs,
                "observed_at": as_of,
                "common_harness_measurement_present": False,
                "competitive_score_claimed": False,
            },
        )
        for system, tracks, refs in raw
    )


def _unique(values: tuple[Any, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _seal_model(model_cls: type[BaseModel], values: dict[str, Any]):
    draft = model_cls.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_cls.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
