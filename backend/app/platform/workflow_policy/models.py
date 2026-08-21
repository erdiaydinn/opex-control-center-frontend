from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonScalar: TypeAlias = str | int | float | bool | None
_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,120}$")
_BLOCKED_PAYLOAD_EXACT_KEYS = frozenset({
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "bearer_token",
    "authorization",
    "authorization_header",
    "auth_header",
    "api_key",
    "private_key",
    "phone",
    "email",
    "address",
    "door_code",
    "national_id",
    "tc_kimlik",
    "command",
    "script",
    "sql",
    "sql_query",
    "sql_text",
    "endpoint_url",
    "url",
    "webhook_url",
})
_BLOCKED_PAYLOAD_FRAGMENTS = (
    "password",
    "secret",
    "phone",
    "email",
    "address",
    "door_code",
    "national_id",
    "tc_kimlik",
)


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _validate_structural_key(key: str, *, kind: str) -> str:
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError(f"invalid {kind} key")
    return key


def _validate_payload_key(key: str, *, kind: str) -> str:
    _validate_structural_key(key, kind=kind)
    lowered = key.lower()
    if lowered in _BLOCKED_PAYLOAD_EXACT_KEYS:
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    if any(fragment in lowered for fragment in _BLOCKED_PAYLOAD_FRAGMENTS):
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    if lowered.endswith("_token") or lowered.endswith("_api_key") or lowered.endswith("_private_key"):
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    if lowered.endswith("_url") or lowered.startswith("url_"):
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    if lowered.endswith("_command") or lowered.startswith("command_"):
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    if lowered.endswith("_script") or lowered.startswith("script_"):
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    if lowered in {"query_sql", "raw_sql", "raw_query"}:
        raise ValueError(f"{kind} key is not permitted in workflow engine payloads")
    return key


def _validate_scalar_map(values: dict[str, JsonScalar], *, kind: str, max_items: int) -> dict[str, JsonScalar]:
    if len(values) > max_items:
        raise ValueError(f"too many {kind} entries")
    for key, value in values.items():
        _validate_payload_key(key, kind=kind)
        if isinstance(value, str) and len(value) > 256:
            raise ValueError(f"{kind} string values must be 256 characters or fewer")
    return values


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"
    DISABLED = "disabled"


class MatchMode(StrEnum):
    ALL = "all"
    ANY = "any"


class ConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


class ActionType(StrEnum):
    NOTIFY = "notify"
    CREATE_TASK = "create_task"
    REQUEST_APPROVAL = "request_approval"
    PROPOSE_DOMAIN_ACTION = "propose_domain_action"
    SCHEDULE_RECHECK = "schedule_recheck"


class ActionEffect(StrEnum):
    INFORMATIONAL = "informational"
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    EMPLOYMENT = "employment"
    SECURITY = "security"


class ExecutionMode(StrEnum):
    AUTOMATIC = "automatic"
    REQUIRES_APPROVAL = "requires_approval"
    PROPOSAL_ONLY = "proposal_only"


HIGH_RISK_EFFECTS = frozenset({
    ActionEffect.FINANCIAL,
    ActionEffect.EMPLOYMENT,
    ActionEffect.SECURITY,
})


class WorkflowScope(StrictFrozenModel):
    country: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=120)
    business_unit: str | None = Field(default=None, max_length=120)
    location_id: str | None = Field(default=None, max_length=160)

    @property
    def specificity(self) -> int:
        return sum(value is not None for value in (self.country, self.region, self.business_unit, self.location_id))


class Condition(StrictFrozenModel):
    fact_key: str
    operator: ConditionOperator
    value: JsonScalar = None
    values: tuple[JsonScalar, ...] = ()

    @model_validator(mode="after")
    def validate_condition(self) -> "Condition":
        _validate_payload_key(self.fact_key, kind="fact")
        if self.operator in {ConditionOperator.IN, ConditionOperator.NOT_IN}:
            if not self.values:
                raise ValueError("in/not_in conditions require values")
            if self.value is not None:
                raise ValueError("in/not_in conditions cannot also use value")
            if len(self.values) > 32:
                raise ValueError("condition value list is too large")
        elif self.values:
            raise ValueError("only in/not_in conditions may use values")
        if self.operator is ConditionOperator.EXISTS and self.value is not None:
            raise ValueError("exists condition cannot use value")
        if isinstance(self.value, str) and len(self.value) > 256:
            raise ValueError("condition value is too long")
        for item in self.values:
            if isinstance(item, str) and len(item) > 256:
                raise ValueError("condition list value is too long")
        return self


class ActionTemplate(StrictFrozenModel):
    action_key: str
    action_type: ActionType
    effect: ActionEffect
    execution_mode: ExecutionMode
    parameters: dict[str, JsonScalar] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action(self) -> "ActionTemplate":
        _validate_structural_key(self.action_key, kind="action")
        _validate_scalar_map(self.parameters, kind="action parameter", max_items=24)
        if self.effect in HIGH_RISK_EFFECTS and self.execution_mode is ExecutionMode.AUTOMATIC:
            raise ValueError("high-risk workflow actions cannot be automatic")
        if self.action_type is ActionType.PROPOSE_DOMAIN_ACTION and self.execution_mode is ExecutionMode.AUTOMATIC:
            raise ValueError("domain mutation actions must remain proposal or approval gated")
        return self


class WorkflowRule(StrictFrozenModel):
    rule_id: str = Field(min_length=1, max_length=160)
    priority: int = Field(default=100, ge=0, le=10000)
    match_mode: MatchMode = MatchMode.ALL
    conditions: tuple[Condition, ...] = ()
    actions: tuple[ActionTemplate, ...] = Field(min_length=1, max_length=16)
    exclusive_group: str | None = Field(default=None, max_length=160)
    stop_processing: bool = False

    @model_validator(mode="after")
    def validate_rule(self) -> "WorkflowRule":
        _validate_structural_key(self.rule_id, kind="rule")
        if len(self.conditions) > 32:
            raise ValueError("workflow rule has too many conditions")
        if self.exclusive_group is not None:
            _validate_structural_key(self.exclusive_group, kind="exclusive group")
        return self


class WorkflowDefinition(StrictFrozenModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    workflow_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    supersedes_version: int | None = Field(default=None, ge=1)
    status: WorkflowStatus
    source_module: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=160)
    scope: WorkflowScope = Field(default_factory=WorkflowScope)
    effective_from: datetime
    effective_to: datetime | None = None
    approved_by: str | None = Field(default=None, max_length=180)
    approved_at: datetime | None = None
    rules: tuple[WorkflowRule, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_definition(self) -> "WorkflowDefinition":
        _validate_structural_key(self.workflow_id, kind="workflow")
        _validate_structural_key(self.source_module, kind="source module")
        _validate_structural_key(self.event_type, kind="event type")
        if self.version == 1 and self.supersedes_version is not None:
            raise ValueError("first workflow version cannot supersede another version")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise ValueError("workflow versions must supersede the immediately prior version")
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("workflow effective_to must be after effective_from")
        if self.status in {WorkflowStatus.APPROVED, WorkflowStatus.EFFECTIVE, WorkflowStatus.SUPERSEDED}:
            if not self.approved_by or self.approved_at is None:
                raise ValueError("approved/effective workflow requires approval provenance")
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("workflow rule ids must be unique")
        return self


class WorkflowEvent(StrictFrozenModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    event_id: str = Field(min_length=1, max_length=180)
    idempotency_key: str = Field(min_length=8, max_length=240)
    source_module: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=160)
    subject_ref: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    scope: WorkflowScope = Field(default_factory=WorkflowScope)
    facts: dict[str, JsonScalar] = Field(default_factory=dict)
    facts_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_event(self) -> "WorkflowEvent":
        _validate_structural_key(self.source_module, kind="source module")
        _validate_structural_key(self.event_type, kind="event type")
        _validate_scalar_map(self.facts, kind="fact", max_items=64)
        return self


class ConditionTrace(StrictFrozenModel):
    fact_key: str
    operator: ConditionOperator
    matched: bool


class RuleTrace(StrictFrozenModel):
    rule_id: str
    priority: int
    matched: bool
    condition_results: tuple[ConditionTrace, ...]


class ActionIntent(StrictFrozenModel):
    tenant_id: str
    intent_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    dedupe_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    workflow_id: str
    workflow_version: int = Field(ge=1)
    event_id: str
    rule_id: str
    action_key: str
    action_type: ActionType
    effect: ActionEffect
    execution_mode: ExecutionMode
    parameters: dict[str, JsonScalar]
    approval_required: bool
    dry_run: bool = False


class EvaluationResult(StrictFrozenModel):
    tenant_id: str
    workflow_id: str
    workflow_version: int
    event_id: str
    dry_run: bool
    traces: tuple[RuleTrace, ...]
    matched_rule_ids: tuple[str, ...]
    action_intents: tuple[ActionIntent, ...]
    decision_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime


class ApprovalDecisionType(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionApprovalDecision(StrictFrozenModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    decision_id: str = Field(min_length=1, max_length=180)
    intent_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: ApprovalDecisionType
    decided_by: str = Field(min_length=1, max_length=180)
    decided_at: datetime
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_decision(self) -> "ActionApprovalDecision":
        if self.decision is ApprovalDecisionType.REJECTED and not (self.reason or "").strip():
            raise ValueError("rejected workflow action requires a reason")
        return self
