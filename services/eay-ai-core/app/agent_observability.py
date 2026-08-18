"""Secret-safe developer observability and diagnostic replay for Jarvis.

This layer is deliberately *not* the authoritative audit log and never replays
business side effects.  It derives a deterministic developer trace from the
existing durable mission definition/checkpoint/specs so engineers can answer:
which step ran, which engine/capability class was involved, what evidence refs
exist, where a retry/ambiguity occurred, and what may be safely inspected next.

Raw prompts, browser page text, request/response payloads, credentials, OTPs and
business input values are outside this contract. Diagnostic replay reconstructs
control flow only; every side-effect step is marked non-replayable.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .mission_execution import (
    MissionExecutionKind,
    MissionExecutionSpec,
    MissionExecutionSummary,
)
from .mission_runtime import MissionDefinition, MissionStatus, StepStatus

AGENT_OBSERVABILITY_CONTRACT = "eay-agent-observability-v1"


class TraceSpanKind(str, Enum):
    MISSION_STEP = "mission_step"
    REASONING = "reasoning"
    CAPABILITY = "capability"


class DiagnosticReplayDisposition(str, Enum):
    INSPECT_EVIDENCE = "inspect_evidence"
    REASONING_REEVALUATION_ALLOWED = "reasoning_reevaluation_allowed"
    READ_ONLY_CAPABILITY_RECHECK_ALLOWED = "read_only_capability_recheck_allowed"
    SIDE_EFFECT_REPLAY_FORBIDDEN = "side_effect_replay_forbidden"
    AMBIGUOUS_EFFECT_RECONCILIATION_REQUIRED = "ambiguous_effect_reconciliation_required"
    NO_ACTION = "no_action"


class AgentTraceSpan(BaseModel):
    contract: str = AGENT_OBSERVABILITY_CONTRACT
    span_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mission_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    kind: TraceSpanKind
    execution_kind: MissionExecutionKind
    status: StepStatus
    attempts: int = Field(ge=0)
    side_effect: bool
    irreversible: bool
    approval_present: bool
    permission_required: bool
    effect_verifier_present: bool
    capability_ref: str | None = None
    reasoning_task_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    error_code: str | None = None
    ambiguous_outcome: bool = False
    raw_prompt_retained: bool = False
    raw_payload_retained: bool = False
    secret_values_retained: bool = False

    @model_validator(mode="after")
    def trace_span_is_nonsecret_and_structurally_consistent(self) -> "AgentTraceSpan":
        if self.raw_prompt_retained or self.raw_payload_retained or self.secret_values_retained:
            raise ValueError("agent_observability_trace_cannot_retain_raw_sensitive_content")
        if self.execution_kind is MissionExecutionKind.CAPABILITY and not self.capability_ref:
            raise ValueError("capability_trace_requires_capability_ref")
        if self.execution_kind is MissionExecutionKind.REASONING and self.capability_ref is not None:
            raise ValueError("reasoning_trace_cannot_claim_capability_ref")
        if self.execution_kind is MissionExecutionKind.REASONING and not self.reasoning_task_ref:
            raise ValueError("reasoning_trace_requires_task_ref")
        if self.execution_kind is MissionExecutionKind.CAPABILITY and self.reasoning_task_ref is not None:
            raise ValueError("capability_trace_cannot_claim_reasoning_task_ref")
        if self.side_effect and not self.effect_verifier_present:
            raise ValueError("side_effect_trace_requires_effect_verifier_presence")
        return self


class AgentDiagnosticTrace(BaseModel):
    contract: str = AGENT_OBSERVABILITY_CONTRACT
    trace_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mission_id: str
    tenant_id: str
    definition_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_sequence: int = Field(ge=0)
    mission_status: MissionStatus
    transitions_executed: int = Field(ge=0)
    spans: tuple[AgentTraceSpan, ...]
    blockers: tuple[str, ...] = ()
    authoritative_audit_replaced: bool = False
    executable_replay_allowed: bool = False
    raw_prompt_retained: bool = False
    raw_payload_retained: bool = False
    secret_values_retained: bool = False

    @model_validator(mode="after")
    def trace_never_becomes_execution_or_audit_truth(self) -> "AgentDiagnosticTrace":
        if self.authoritative_audit_replaced:
            raise ValueError("agent_observability_never_replaces_authoritative_audit")
        if self.executable_replay_allowed:
            raise ValueError("agent_observability_never_allows_executable_replay")
        if self.raw_prompt_retained or self.raw_payload_retained or self.secret_values_retained:
            raise ValueError("agent_observability_trace_cannot_retain_raw_sensitive_content")
        return self


class DiagnosticReplayStep(BaseModel):
    span_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    step_id: str
    disposition: DiagnosticReplayDisposition
    evidence_refs: tuple[str, ...] = ()
    executable: bool = False
    side_effect_replay_allowed: bool = False

    @model_validator(mode="after")
    def replay_step_is_diagnostic_only(self) -> "DiagnosticReplayStep":
        if self.executable or self.side_effect_replay_allowed:
            raise ValueError("diagnostic_replay_cannot_execute_business_actions")
        return self


class DiagnosticReplayPlan(BaseModel):
    contract: str = AGENT_OBSERVABILITY_CONTRACT
    trace_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    steps: tuple[DiagnosticReplayStep, ...]
    executable: bool = False
    mutation_allowed: bool = False
    requires_fresh_authorization_for_any_future_write: bool = True

    @model_validator(mode="after")
    def plan_is_never_a_write_replayer(self) -> "DiagnosticReplayPlan":
        if self.executable or self.mutation_allowed:
            raise ValueError("diagnostic_replay_plan_must_be_non_executable")
        if not self.requires_fresh_authorization_for_any_future_write:
            raise ValueError("future_write_after_diagnostic_replay_requires_fresh_authorization")
        return self


def _span_id(*, mission_id: str, step_id: str, sequence: int, definition_fingerprint: str) -> str:
    canonical = json.dumps(
        {
            "contract": AGENT_OBSERVABILITY_CONTRACT,
            "mission_id": mission_id,
            "step_id": step_id,
            "sequence": sequence,
            "definition_fingerprint": definition_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _trace_id(*, definition: MissionDefinition, summary: MissionExecutionSummary) -> str:
    canonical = json.dumps(
        {
            "contract": AGENT_OBSERVABILITY_CONTRACT,
            "mission_id": definition.mission_id,
            "tenant_id": definition.tenant_id,
            "definition_fingerprint": definition.fingerprint(),
            "checkpoint_sequence": summary.checkpoint.sequence,
            "mission_status": summary.checkpoint.status.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_agent_diagnostic_trace(
    *,
    definition: MissionDefinition,
    specs: tuple[MissionExecutionSpec, ...],
    summary: MissionExecutionSummary,
) -> AgentDiagnosticTrace:
    if summary.checkpoint.mission_id != definition.mission_id:
        raise ValueError("agent_observability_mission_identity_mismatch")
    if summary.checkpoint.tenant_id != definition.tenant_id:
        raise ValueError("agent_observability_tenant_identity_mismatch")
    if summary.checkpoint.definition_fingerprint != definition.fingerprint():
        raise ValueError("agent_observability_definition_drift")

    spec_map = {item.step_id: item for item in specs}
    if len(spec_map) != len(specs):
        raise ValueError("agent_observability_specs_must_be_unique")
    expected = {item.step_id for item in definition.steps}
    if set(spec_map) != expected:
        raise ValueError("agent_observability_specs_must_cover_definition_exactly")

    state_map = {item.step_id: item for item in summary.checkpoint.steps}
    spans: list[AgentTraceSpan] = []
    for sequence, step in enumerate(definition.steps, start=1):
        state = state_map[step.step_id]
        spec = spec_map[step.step_id]
        if spec.kind is MissionExecutionKind.REASONING:
            span_kind = TraceSpanKind.REASONING
            reasoning_task_ref = (
                None if spec.intelligence_task is None else spec.intelligence_task.task_id
            )
            capability_ref = None
        else:
            span_kind = TraceSpanKind.CAPABILITY
            reasoning_task_ref = None
            capability_ref = spec.capability_ref
        spans.append(
            AgentTraceSpan(
                span_id=_span_id(
                    mission_id=definition.mission_id,
                    step_id=step.step_id,
                    sequence=sequence,
                    definition_fingerprint=definition.fingerprint(),
                ),
                mission_id=definition.mission_id,
                tenant_id=definition.tenant_id,
                step_id=step.step_id,
                sequence=sequence,
                kind=span_kind,
                execution_kind=spec.kind,
                status=state.status,
                attempts=state.attempts,
                side_effect=step.side_effect,
                irreversible=step.irreversible,
                approval_present=bool(state.approval_ref),
                permission_required=bool(step.required_permission),
                effect_verifier_present=bool(step.effect_verifier_ref),
                capability_ref=capability_ref,
                reasoning_task_ref=reasoning_task_ref,
                evidence_refs=state.evidence_refs,
                error_code=state.last_error,
                ambiguous_outcome=state.ambiguous_outcome,
            )
        )

    return AgentDiagnosticTrace(
        trace_id=_trace_id(definition=definition, summary=summary),
        mission_id=definition.mission_id,
        tenant_id=definition.tenant_id,
        definition_fingerprint=definition.fingerprint(),
        checkpoint_sequence=summary.checkpoint.sequence,
        mission_status=summary.checkpoint.status,
        transitions_executed=summary.transitions_executed,
        spans=tuple(spans),
        blockers=summary.blockers,
    )


def build_diagnostic_replay_plan(trace: AgentDiagnosticTrace) -> DiagnosticReplayPlan:
    steps: list[DiagnosticReplayStep] = []
    for span in trace.spans:
        if span.side_effect:
            disposition = (
                DiagnosticReplayDisposition.AMBIGUOUS_EFFECT_RECONCILIATION_REQUIRED
                if span.ambiguous_outcome
                else DiagnosticReplayDisposition.SIDE_EFFECT_REPLAY_FORBIDDEN
            )
        elif span.status in {StepStatus.FAILED, StepStatus.BLOCKED}:
            disposition = DiagnosticReplayDisposition.INSPECT_EVIDENCE
        elif span.execution_kind is MissionExecutionKind.REASONING:
            disposition = DiagnosticReplayDisposition.REASONING_REEVALUATION_ALLOWED
        elif span.execution_kind is MissionExecutionKind.CAPABILITY:
            disposition = DiagnosticReplayDisposition.READ_ONLY_CAPABILITY_RECHECK_ALLOWED
        else:  # pragma: no cover - enum exhaustiveness
            disposition = DiagnosticReplayDisposition.NO_ACTION
        steps.append(
            DiagnosticReplayStep(
                span_id=span.span_id,
                step_id=span.step_id,
                disposition=disposition,
                evidence_refs=span.evidence_refs,
            )
        )
    return DiagnosticReplayPlan(trace_id=trace.trace_id, steps=tuple(steps))
