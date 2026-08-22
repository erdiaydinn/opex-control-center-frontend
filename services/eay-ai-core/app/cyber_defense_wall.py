"""Layered defensive wall authority for EAY Jarvis.

This module models defense-in-depth against combined attack chains. It does not
contain exploit procedures or offensive execution. A wall is considered READY
only when required controls have current evidence and no critical coverage gap.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

CYBER_DEFENSE_WALL_CONTRACT = "eay-cyber-defense-wall-v1"


class DefenseWall(str, Enum):
    EDGE = "edge"
    IDENTITY = "identity"
    APPLICATION_API = "application_api"
    DATA_TENANT = "data_tenant"
    AI_AGENT = "ai_agent"
    SUPPLY_CHAIN = "supply_chain"
    RUNTIME_DETECTION = "runtime_detection"
    RECOVERY = "recovery"


class AttackChainStage(str, Enum):
    RECON_INITIAL_ACCESS = "recon_initial_access"
    IDENTITY_ABUSE = "identity_abuse"
    APPLICATION_EXPLOITATION = "application_exploitation"
    PRIVILEGE_LATERAL_MOVEMENT = "privilege_lateral_movement"
    DATA_ACCESS_EXFILTRATION = "data_access_exfiltration"
    AI_TOOL_ABUSE = "ai_tool_abuse"
    PERSISTENCE_IMPACT = "persistence_impact"
    COVER_TRACKS_RECOVERY_PRESSURE = "cover_tracks_recovery_pressure"


class DefenseControlKind(str, Enum):
    PREVENT = "prevent"
    DETECT = "detect"
    CONTAIN = "contain"
    RECOVER = "recover"


class DefenseControlEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_WALL_CONTRACT
    control_id: str = Field(min_length=1)
    wall: DefenseWall
    kind: DefenseControlKind
    stage_coverage: tuple[AttackChainStage, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    expires_at: datetime
    enabled: bool
    fail_closed: bool
    company_scoped: bool
    production_observed: bool = False
    automatic_offensive_action_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def control_is_defensive(self) -> DefenseControlEvidence:
        _aware(self.observed_at, "cyber_wall_observed_at_requires_timezone")
        _aware(self.expires_at, "cyber_wall_expires_at_requires_timezone")
        if self.expires_at <= self.observed_at:
            raise ValueError("cyber_wall_evidence_expiry_invalid")
        if len(self.stage_coverage) != len(set(self.stage_coverage)):
            raise ValueError("cyber_wall_stage_coverage_must_be_unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("cyber_wall_evidence_refs_must_be_unique")
        if self.automatic_offensive_action_permitted or self.execution_authority_granted:
            raise ValueError("cyber_wall_offensive_or_execution_authority_forbidden")
        _verify(self, "cyber_wall_control_fingerprint_mismatch")
        return self


class WallReadiness(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class DefenseWallReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_WALL_CONTRACT
    wall: DefenseWall
    as_of: datetime
    controls: tuple[DefenseControlEvidence, ...] = Field(min_length=1)
    required_control_ids: tuple[str, ...] = Field(min_length=1)
    missing_control_ids: tuple[str, ...]
    stale_control_ids: tuple[str, ...]
    non_fail_closed_control_ids: tuple[str, ...]
    readiness: WallReadiness
    production_ready_claim_allowed: bool
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def wall_requires_complete_current_evidence(self) -> DefenseWallReceipt:
        _aware(self.as_of, "cyber_wall_receipt_as_of_requires_timezone")
        if any(control.wall is not self.wall for control in self.controls):
            raise ValueError("cyber_wall_cross_wall_control_forbidden")
        ids = tuple(control.control_id for control in self.controls)
        if len(ids) != len(set(ids)):
            raise ValueError("cyber_wall_duplicate_control")
        if self.execution_authority_granted:
            raise ValueError("cyber_wall_receipt_never_grants_execution_authority")
        expected_ready = (
            not self.missing_control_ids
            and not self.stale_control_ids
            and not self.non_fail_closed_control_ids
            and all(control.enabled for control in self.controls if control.control_id in self.required_control_ids)
        )
        if self.readiness is WallReadiness.READY and not expected_ready:
            raise ValueError("cyber_wall_ready_without_complete_controls")
        if self.production_ready_claim_allowed:
            required = [c for c in self.controls if c.control_id in self.required_control_ids]
            if self.readiness is not WallReadiness.READY or not required:
                raise ValueError("cyber_wall_production_claim_requires_ready_wall")
            if not all(c.production_observed and c.company_scoped for c in required):
                raise ValueError("cyber_wall_production_claim_requires_company_production_evidence")
        _verify(self, "cyber_wall_receipt_fingerprint_mismatch")
        return self


class CombinedAttackChainAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_WALL_CONTRACT
    chain_id: str = Field(min_length=1)
    as_of: datetime
    stages: tuple[AttackChainStage, ...] = Field(min_length=1)
    wall_receipts: tuple[DefenseWallReceipt, ...] = Field(min_length=1)
    uncovered_stages: tuple[AttackChainStage, ...]
    single_point_of_failure_stages: tuple[AttackChainStage, ...]
    defense_in_depth_complete: bool
    production_security_claim_allowed: bool
    offensive_simulation_permitted: bool = False
    production_mutation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def chain_is_defense_only(self) -> CombinedAttackChainAssessment:
        _aware(self.as_of, "cyber_chain_as_of_requires_timezone")
        if len(self.stages) != len(set(self.stages)):
            raise ValueError("cyber_chain_stages_must_be_unique")
        walls = tuple(receipt.wall for receipt in self.wall_receipts)
        if len(walls) != len(set(walls)):
            raise ValueError("cyber_chain_wall_receipts_must_be_unique")
        if (
            self.offensive_simulation_permitted
            or self.production_mutation_permitted
            or self.execution_authority_granted
        ):
            raise ValueError("cyber_chain_offensive_or_write_authority_forbidden")
        if self.defense_in_depth_complete and (
            self.uncovered_stages or self.single_point_of_failure_stages
        ):
            raise ValueError("cyber_chain_depth_claim_has_coverage_gap")
        if self.production_security_claim_allowed:
            if not self.defense_in_depth_complete:
                raise ValueError("cyber_chain_production_claim_requires_defense_in_depth")
            if not all(r.production_ready_claim_allowed for r in self.wall_receipts):
                raise ValueError("cyber_chain_production_claim_requires_all_wall_evidence")
        _verify(self, "cyber_chain_fingerprint_mismatch")
        return self


DEFAULT_REQUIRED_CONTROLS: dict[DefenseWall, tuple[str, ...]] = {
    DefenseWall.EDGE: (
        "edge.waf_managed_rules",
        "edge.rate_limit",
        "edge.bot_abuse_control",
        "edge.upload_quarantine",
    ),
    DefenseWall.IDENTITY: (
        "identity.oidc_mfa",
        "identity.short_lived_session",
        "identity.service_identity",
        "identity.single_use_grant",
        "identity.revocation",
    ),
    DefenseWall.APPLICATION_API: (
        "api.server_authorization",
        "api.object_level_authorization",
        "api.schema_validation",
        "api.idempotency_replay",
        "api.egress_allowlist",
    ),
    DefenseWall.DATA_TENANT: (
        "data.tenant_binding",
        "data.rls",
        "data.encryption",
        "data.secret_kms",
        "data.audit_chain",
    ),
    DefenseWall.AI_AGENT: (
        "ai.tool_allowlist",
        "ai.context_tenant_binding",
        "ai.prompt_injection_boundary",
        "ai.dlp_output_guard",
        "ai.no_direct_production_authority",
    ),
    DefenseWall.SUPPLY_CHAIN: (
        "supply.locked_dependencies",
        "supply.secret_scan",
        "supply.sast_dependency_scan",
        "supply.pinned_ci_actions",
        "supply.artifact_provenance",
    ),
    DefenseWall.RUNTIME_DETECTION: (
        "runtime.network_segmentation",
        "runtime.least_privilege",
        "runtime.telemetry",
        "runtime.sigma_detection",
        "runtime.incident_alerting",
    ),
    DefenseWall.RECOVERY: (
        "recovery.immutable_backup",
        "recovery.restore_test",
        "recovery.key_rotation",
        "recovery.incident_playbook",
        "recovery.audit_retention",
    ),
}


def build_control_evidence(
    *,
    control_id: str,
    wall: DefenseWall,
    kind: DefenseControlKind,
    stage_coverage: tuple[AttackChainStage, ...],
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    expires_at: datetime,
    enabled: bool = True,
    fail_closed: bool = True,
    company_scoped: bool = True,
    production_observed: bool = False,
) -> DefenseControlEvidence:
    return _seal(
        DefenseControlEvidence,
        {
            "contract": CYBER_DEFENSE_WALL_CONTRACT,
            "control_id": control_id,
            "wall": wall,
            "kind": kind,
            "stage_coverage": stage_coverage,
            "evidence_refs": evidence_refs,
            "observed_at": observed_at,
            "expires_at": expires_at,
            "enabled": enabled,
            "fail_closed": fail_closed,
            "company_scoped": company_scoped,
            "production_observed": production_observed,
            "automatic_offensive_action_permitted": False,
            "execution_authority_granted": False,
        },
    )


def assess_wall(
    *,
    wall: DefenseWall,
    controls: tuple[DefenseControlEvidence, ...],
    as_of: datetime,
    required_control_ids: tuple[str, ...] | None = None,
) -> DefenseWallReceipt:
    required = required_control_ids or DEFAULT_REQUIRED_CONTROLS[wall]
    by_id = {control.control_id: control for control in controls if control.wall is wall}
    missing = tuple(sorted(set(required) - set(by_id)))
    stale = tuple(sorted(cid for cid in required if cid in by_id and by_id[cid].expires_at <= as_of))
    non_fail_closed = tuple(
        sorted(cid for cid in required if cid in by_id and not by_id[cid].fail_closed)
    )
    disabled = tuple(cid for cid in required if cid in by_id and not by_id[cid].enabled)
    if missing or stale or disabled:
        readiness = WallReadiness.BLOCKED
    elif non_fail_closed:
        readiness = WallReadiness.DEGRADED
    else:
        readiness = WallReadiness.READY
    required_controls = [by_id[cid] for cid in required if cid in by_id]
    production_claim = bool(
        readiness is WallReadiness.READY
        and required_controls
        and all(c.production_observed and c.company_scoped for c in required_controls)
    )
    return _seal(
        DefenseWallReceipt,
        {
            "contract": CYBER_DEFENSE_WALL_CONTRACT,
            "wall": wall,
            "as_of": as_of,
            "controls": tuple(by_id.values()),
            "required_control_ids": required,
            "missing_control_ids": missing,
            "stale_control_ids": stale,
            "non_fail_closed_control_ids": non_fail_closed,
            "readiness": readiness,
            "production_ready_claim_allowed": production_claim,
            "execution_authority_granted": False,
        },
    )


def assess_combined_attack_chain(
    *,
    chain_id: str,
    stages: tuple[AttackChainStage, ...],
    wall_receipts: tuple[DefenseWallReceipt, ...],
    as_of: datetime,
) -> CombinedAttackChainAssessment:
    coverage: dict[AttackChainStage, set[DefenseWall]] = {stage: set() for stage in stages}
    for receipt in wall_receipts:
        if receipt.readiness is not WallReadiness.READY:
            continue
        for control in receipt.controls:
            if not control.enabled or control.expires_at <= as_of:
                continue
            for stage in control.stage_coverage:
                if stage in coverage:
                    coverage[stage].add(receipt.wall)
    uncovered = tuple(stage for stage, walls in coverage.items() if not walls)
    single = tuple(stage for stage, walls in coverage.items() if len(walls) == 1)
    depth_complete = not uncovered and not single and len(set(r.wall for r in wall_receipts)) >= 2
    production_claim = bool(
        depth_complete
        and wall_receipts
        and all(receipt.production_ready_claim_allowed for receipt in wall_receipts)
    )
    return _seal(
        CombinedAttackChainAssessment,
        {
            "contract": CYBER_DEFENSE_WALL_CONTRACT,
            "chain_id": chain_id,
            "as_of": as_of,
            "stages": stages,
            "wall_receipts": wall_receipts,
            "uncovered_stages": uncovered,
            "single_point_of_failure_stages": single,
            "defense_in_depth_complete": depth_complete,
            "production_security_claim_allowed": production_claim,
            "offensive_simulation_permitted": False,
            "production_mutation_permitted": False,
            "execution_authority_granted": False,
        },
    )


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


def _seal(model_cls: type[BaseModel], values: Mapping[str, Any]):
    draft = model_cls.model_construct(**dict(values), fingerprint="0" * 64)
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
