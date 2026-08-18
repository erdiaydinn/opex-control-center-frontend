"""Real-device acceptance matrix for Jarvis Windows spatial interaction.

Repository tests and synthetic geometry remain regression evidence only. This
module requires explicit device-lab/controlled-field evidence for the Windows
conditions most likely to break spatial control: mixed DPI, portrait monitors,
negative coordinates, maximized windows, hotplug, RDP, virtual desktops and UAC
integrity boundaries. Unsupported conditions must fail closed; UAC/elevation is
never bypassed.
"""

from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel, Field, model_validator

SPATIAL_DEVICE_ACCEPTANCE_CONTRACT = "eay-spatial-device-acceptance-v1"


class DeviceEvidenceTier(str, Enum):
    SYNTHETIC = "synthetic"
    DEVICE_LAB = "device_lab"
    CONTROLLED_FIELD = "controlled_field"


class WindowsSpatialScenario(str, Enum):
    MIXED_DPI = "mixed_dpi"
    PORTRAIT_LANDSCAPE = "portrait_landscape"
    NEGATIVE_COORDINATES = "negative_coordinates"
    MAXIMIZED_WINDOW = "maximized_window"
    MONITOR_HOTPLUG = "monitor_hotplug"
    RDP_SESSION = "rdp_session"
    VIRTUAL_DESKTOP = "virtual_desktop"
    UAC_ELEVATION_BOUNDARY = "uac_elevation_boundary"


_REQUIRED_SCENARIOS = frozenset(WindowsSpatialScenario)


class WindowsSpatialDeviceProfile(BaseModel):
    profile_ref: str = Field(min_length=1)
    os_build_ref: str = Field(min_length=1)
    machine_ref: str = Field(min_length=1)
    monitor_topology_ref: str = Field(min_length=1)
    dpi_profile_ref: str = Field(min_length=1)
    camera_device_ref: str = Field(min_length=1)
    driver_evidence_refs: tuple[str, ...] = Field(min_length=1)
    raw_device_identifiers_retained: bool = False

    @model_validator(mode="after")
    def profile_is_opaque(self) -> "WindowsSpatialDeviceProfile":
        if self.raw_device_identifiers_retained:
            raise ValueError("spatial_device_profile_cannot_retain_raw_identifiers")
        return self

    @property
    def environment_fingerprint(self) -> str:
        payload = "|".join(
            (
                self.os_build_ref,
                self.machine_ref,
                self.monitor_topology_ref,
                self.dpi_profile_ref,
                self.camera_device_ref,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WindowsSpatialAcceptanceCase(BaseModel):
    case_id: str = Field(min_length=1)
    scenario: WindowsSpatialScenario
    evidence_tier: DeviceEvidenceTier
    environment_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    intended_action_supported: bool
    intended_action_completed: bool
    fail_closed_when_unsupported: bool
    correct_window_targeted: bool
    geometry_inside_work_area: bool
    duplicate_move_count: int = Field(ge=0)
    wrong_window_move_count: int = Field(ge=0)
    uac_or_integrity_bypass_attempted: bool = False
    raw_sensor_leakage: bool = False
    application_content_leakage: bool = False
    latency_ms: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class SpatialDeviceAcceptanceRun(BaseModel):
    contract: str = SPATIAL_DEVICE_ACCEPTANCE_CONTRACT
    system_ref: str = Field(min_length=1)
    profile: WindowsSpatialDeviceProfile
    evidence_tier: DeviceEvidenceTier
    cases: tuple[WindowsSpatialAcceptanceCase, ...] = Field(min_length=1)
    independent_observer_ref: str = Field(min_length=1)
    repository_ci_only: bool = False

    @model_validator(mode="after")
    def run_is_environment_consistent(self) -> "SpatialDeviceAcceptanceRun":
        if any(item.evidence_tier is not self.evidence_tier for item in self.cases):
            raise ValueError("spatial_device_acceptance_mixed_evidence_tier")
        if any(item.environment_fingerprint != self.profile.environment_fingerprint for item in self.cases):
            raise ValueError("spatial_device_acceptance_environment_mismatch")
        if self.evidence_tier is not DeviceEvidenceTier.SYNTHETIC and self.repository_ci_only:
            raise ValueError("spatial_device_acceptance_real_tier_cannot_be_repository_only")
        return self


class SpatialDeviceAcceptanceDecision(BaseModel):
    contract: str = SPATIAL_DEVICE_ACCEPTANCE_CONTRACT
    device_lab_accepted: bool = False
    controlled_field_accepted: bool = False
    production_claim_allowed: bool = False
    wrong_window_moves: int = Field(ge=0)
    duplicate_moves: int = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)
    covered_scenarios: frozenset[WindowsSpatialScenario]
    blockers: tuple[str, ...] = ()
    automatic_production_promotion_allowed: bool = False

    @model_validator(mode="after")
    def decision_never_auto_promotes(self) -> "SpatialDeviceAcceptanceDecision":
        if self.automatic_production_promotion_allowed:
            raise ValueError("spatial_device_acceptance_never_auto_promotes")
        if self.production_claim_allowed and not self.controlled_field_accepted:
            raise ValueError("spatial_device_acceptance_production_claim_requires_field")
        return self


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
    return ordered[index]


def evaluate_spatial_device_acceptance(run: SpatialDeviceAcceptanceRun) -> SpatialDeviceAcceptanceDecision:
    blockers: list[str] = []
    covered = frozenset(item.scenario for item in run.cases)
    missing = _REQUIRED_SCENARIOS - covered
    if missing:
        blockers.append("spatial_device_acceptance_required_scenarios_missing")
    if len(run.cases) < len(_REQUIRED_SCENARIOS):
        blockers.append("spatial_device_acceptance_minimum_case_count_not_met")

    wrong = sum(item.wrong_window_move_count for item in run.cases)
    duplicates = sum(item.duplicate_move_count for item in run.cases)
    if wrong:
        blockers.append("spatial_device_acceptance_wrong_window_move")
    if duplicates:
        blockers.append("spatial_device_acceptance_duplicate_move")
    if any(item.uac_or_integrity_bypass_attempted for item in run.cases):
        blockers.append("spatial_device_acceptance_uac_bypass_forbidden")
    if any(item.raw_sensor_leakage or item.application_content_leakage for item in run.cases):
        blockers.append("spatial_device_acceptance_content_leakage")
    if any(item.intended_action_supported and not item.intended_action_completed for item in run.cases):
        blockers.append("spatial_device_acceptance_supported_action_failed")
    if any(not item.intended_action_supported and not item.fail_closed_when_unsupported for item in run.cases):
        blockers.append("spatial_device_acceptance_unsupported_case_not_fail_closed")
    if any(item.intended_action_supported and not item.correct_window_targeted for item in run.cases):
        blockers.append("spatial_device_acceptance_target_mismatch")
    if any(item.intended_action_supported and not item.geometry_inside_work_area for item in run.cases):
        blockers.append("spatial_device_acceptance_geometry_invalid")

    latency = _p95([item.latency_ms for item in run.cases])
    if latency > 400:
        blockers.append("spatial_device_acceptance_latency_above_floor")
    if run.evidence_tier is DeviceEvidenceTier.SYNTHETIC:
        blockers.append("spatial_device_acceptance_real_device_evidence_required")

    lab = not blockers and run.evidence_tier in {
        DeviceEvidenceTier.DEVICE_LAB,
        DeviceEvidenceTier.CONTROLLED_FIELD,
    }
    field = not blockers and run.evidence_tier is DeviceEvidenceTier.CONTROLLED_FIELD
    return SpatialDeviceAcceptanceDecision(
        device_lab_accepted=lab,
        controlled_field_accepted=field,
        production_claim_allowed=field,
        wrong_window_moves=wrong,
        duplicate_moves=duplicates,
        p95_latency_ms=latency,
        covered_scenarios=covered,
        blockers=tuple(dict.fromkeys(blockers)),
    )
