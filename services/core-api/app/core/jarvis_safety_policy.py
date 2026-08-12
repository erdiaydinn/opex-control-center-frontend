"""Fail-closed safety policy kernel for governed Jarvis tool execution.

The policy registry is immutable and server-owned. It defines risk, data
sensitivity, side-effect class, approval requirements, execution budgets and
bounded argument complexity for every executable AI tool. Unknown or
unregistered tools fail closed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_tool_authorization import TOOL_REQUIRED_SCOPES, AiToolName

JARVIS_SAFETY_POLICY_VERSION = 1

RiskClass = Literal["low", "medium", "high", "critical"]
DataSensitivity = Literal["internal", "confidential", "restricted"]
SideEffectClass = Literal["none", "read", "write", "irreversible"]


class JarvisSafetyPolicyError(RuntimeError):
    """Base fail-closed safety-policy failure."""


class JarvisSafetyPolicyDenied(JarvisSafetyPolicyError):
    """The requested invocation is not allowed by the safety kernel."""


class ToolSafetyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = JARVIS_SAFETY_POLICY_VERSION
    risk_class: RiskClass
    data_sensitivity: DataSensitivity
    side_effect_class: SideEffectClass
    requires_human_approval: bool
    maximum_bytes_billed: int = Field(ge=1, le=10 * 1024 * 1024 * 1024)
    timeout_ms: int = Field(ge=1000, le=120_000)
    max_rows: int = Field(ge=1, le=500)
    max_argument_depth: int = Field(ge=1, le=16)
    max_argument_nodes: int = Field(ge=1, le=5000)
    max_argument_string_bytes: int = Field(ge=1, le=256 * 1024)


class ToolExecutionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: AiToolName
    policy_version: Literal[1] = JARVIS_SAFETY_POLICY_VERSION
    risk_class: RiskClass
    data_sensitivity: DataSensitivity
    side_effect_class: SideEffectClass
    requires_human_approval: bool
    maximum_bytes_billed: int
    timeout_ms: int
    max_rows: int
    safety_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


_TOOL_POLICIES = {
    "ops_kpi_query": ToolSafetyPolicy(
        risk_class="low",
        data_sensitivity="internal",
        side_effect_class="read",
        requires_human_approval=False,
        maximum_bytes_billed=250 * 1024 * 1024,
        timeout_ms=20_000,
        max_rows=500,
        max_argument_depth=8,
        max_argument_nodes=1000,
        max_argument_string_bytes=64 * 1024,
    ),
    "catalog_query": ToolSafetyPolicy(
        risk_class="low",
        data_sensitivity="internal",
        side_effect_class="read",
        requires_human_approval=False,
        maximum_bytes_billed=250 * 1024 * 1024,
        timeout_ms=20_000,
        max_rows=500,
        max_argument_depth=8,
        max_argument_nodes=1000,
        max_argument_string_bytes=64 * 1024,
    ),
    "regulatory_impact_query": ToolSafetyPolicy(
        risk_class="medium",
        data_sensitivity="confidential",
        side_effect_class="read",
        requires_human_approval=False,
        maximum_bytes_billed=250 * 1024 * 1024,
        timeout_ms=20_000,
        max_rows=250,
        max_argument_depth=8,
        max_argument_nodes=1000,
        max_argument_string_bytes=64 * 1024,
    ),
}

TOOL_SAFETY_POLICIES = MappingProxyType(_TOOL_POLICIES)


def _canonical_fingerprint(tool: str, policy: ToolSafetyPolicy) -> str:
    encoded = json.dumps(
        {"tool": tool, **policy.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_registry() -> None:
    registered = set(TOOL_SAFETY_POLICIES)
    authorized = set(TOOL_REQUIRED_SCOPES)
    if registered != authorized:
        raise RuntimeError("Jarvis safety registry must exactly cover authorized tools")

    for tool, policy in TOOL_SAFETY_POLICIES.items():
        if (
            policy.side_effect_class in {"write", "irreversible"}
            and not policy.requires_human_approval
        ):
            raise RuntimeError(f"Jarvis mutating tool {tool} requires human approval")
        if policy.risk_class == "critical":
            raise RuntimeError(f"Critical Jarvis tool {tool} cannot auto-execute")


_validate_registry()


def _measure_arguments(
    value: Any,
    *,
    depth: int,
    policy: ToolSafetyPolicy,
    counters: dict[str, int],
) -> None:
    if depth > policy.max_argument_depth:
        raise JarvisSafetyPolicyDenied("AI tool arguments exceed maximum depth")

    counters["nodes"] += 1
    if counters["nodes"] > policy.max_argument_nodes:
        raise JarvisSafetyPolicyDenied("AI tool arguments exceed maximum complexity")

    if isinstance(value, str):
        counters["string_bytes"] += len(value.encode("utf-8"))
        if counters["string_bytes"] > policy.max_argument_string_bytes:
            raise JarvisSafetyPolicyDenied("AI tool arguments exceed maximum text size")
        return

    if value is None or isinstance(value, (bool, int, float)):
        return

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise JarvisSafetyPolicyDenied("AI tool arguments contain a non-string key")
            counters["string_bytes"] += len(key.encode("utf-8"))
            if counters["string_bytes"] > policy.max_argument_string_bytes:
                raise JarvisSafetyPolicyDenied("AI tool arguments exceed maximum text size")
            _measure_arguments(
                child,
                depth=depth + 1,
                policy=policy,
                counters=counters,
            )
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _measure_arguments(
                child,
                depth=depth + 1,
                policy=policy,
                counters=counters,
            )
        return

    raise JarvisSafetyPolicyDenied("AI tool arguments contain an unsupported value")


def execution_envelope(
    tool: AiToolName,
    *,
    arguments: Mapping[str, Any],
) -> ToolExecutionEnvelope:
    policy = TOOL_SAFETY_POLICIES.get(tool)
    if policy is None:
        raise JarvisSafetyPolicyDenied("AI tool is not registered in the safety kernel")

    counters = {"nodes": 0, "string_bytes": 0}
    _measure_arguments(arguments, depth=1, policy=policy, counters=counters)

    if policy.side_effect_class in {"write", "irreversible"}:
        raise JarvisSafetyPolicyDenied("Mutating AI tools require a separate approval workflow")
    if policy.risk_class == "critical":
        raise JarvisSafetyPolicyDenied("Critical AI tools cannot auto-execute")

    return ToolExecutionEnvelope(
        tool=tool,
        risk_class=policy.risk_class,
        data_sensitivity=policy.data_sensitivity,
        side_effect_class=policy.side_effect_class,
        requires_human_approval=policy.requires_human_approval,
        maximum_bytes_billed=policy.maximum_bytes_billed,
        timeout_ms=policy.timeout_ms,
        max_rows=policy.max_rows,
        safety_policy_fingerprint=_canonical_fingerprint(tool, policy),
    )
