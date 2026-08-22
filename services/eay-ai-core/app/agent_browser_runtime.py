"""Governed read-only agent-browser harness for managed corporate sessions.

This runtime complements, rather than replaces, the canonical Playwright
executor.  It is intentionally narrower: when Jarvis attaches to an already
running corporate Chromium session over CDP, agent-browser is used only for
semantic snapshots/read/get operations.  Mutating browser actions remain on
the EAY Playwright mission/effect-verification path.

Why the split matters:
- upstream agent-browser cannot combine its browser-level ``--allowed-domains``
  containment with pre-existing CDP sessions;
- corporate Okta/SSO sessions are exactly the case where reusing an existing
  managed browser is valuable;
- therefore this adapter requires a separate EAY network-egress boundary
  evidence reference, pins the session to one tab, enables content-boundary
  markers, and always applies a deny-by-default read-only action policy.

Page content is transient.  The serializable receipt never contains the page
text, DOM snapshot, URL query string, credentials, or authentication tokens.
"""

from __future__ import annotations

import json
import re
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, model_validator

AGENT_BROWSER_RUNTIME_CONTRACT = "eay-agent-browser-read-runtime-v1"
DEFAULT_READONLY_POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "agent_browser_corporate_readonly_policy.json"
)
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


class AgentBrowserReadKind(str, Enum):
    SNAPSHOT = "snapshot"
    READ_ACTIVE = "read_active"
    GET_URL = "get_url"
    GET_TEXT = "get_text"


class AgentBrowserReadCommand(BaseModel):
    command_id: str = Field(min_length=1)
    kind: AgentBrowserReadKind
    selector: str | None = None
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=60.0)

    @model_validator(mode="after")
    def selector_matches_command(self) -> "AgentBrowserReadCommand":
        if self.kind is AgentBrowserReadKind.GET_TEXT and not self.selector:
            raise ValueError("agent_browser_get_text_requires_selector")
        if self.kind is not AgentBrowserReadKind.GET_TEXT and self.selector is not None:
            raise ValueError("agent_browser_selector_only_allowed_for_get_text")
        return self


class AgentBrowserCorporateSessionConfig(BaseModel):
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    auth_context_ref: str = Field(min_length=1)
    network_egress_boundary_ref: str = Field(min_length=1)
    allowed_hosts: frozenset[str] = Field(min_length=1)
    session_name: str = Field(min_length=3, max_length=64)
    cdp_endpoint: str = "http://127.0.0.1:9222"
    allow_remote_cdp: bool = False
    pin_tab: bool = True
    content_boundaries: bool = True
    maximum_output_chars: int = Field(default=50000, ge=1000, le=100000)
    action_policy_path: str = str(DEFAULT_READONLY_POLICY_PATH)
    binary: str = "agent-browser"

    @model_validator(mode="after")
    def corporate_attach_is_fail_closed(self) -> "AgentBrowserCorporateSessionConfig":
        if not _SESSION_RE.fullmatch(self.session_name):
            raise ValueError("agent_browser_session_name_invalid")
        if self.binary != "agent-browser":
            raise ValueError("agent_browser_binary_override_forbidden")
        if not self.pin_tab:
            raise ValueError("agent_browser_corporate_session_requires_pin_tab")
        if not self.content_boundaries:
            raise ValueError("agent_browser_corporate_session_requires_content_boundaries")
        if not self.network_egress_boundary_ref.strip():
            raise ValueError("agent_browser_corporate_session_requires_egress_boundary_ref")

        parsed = urlparse(self.cdp_endpoint)
        if parsed.scheme not in {"http", "https", "ws", "wss"}:
            raise ValueError("agent_browser_cdp_scheme_not_allowed")
        host = (parsed.hostname or "").casefold()
        if not host:
            raise ValueError("agent_browser_cdp_host_required")
        if parsed.port is None:
            raise ValueError("agent_browser_cdp_port_required")
        if not self.allow_remote_cdp and host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("agent_browser_remote_cdp_requires_explicit_authorization")

        normalized_hosts = frozenset(item.casefold().rstrip(".") for item in self.allowed_hosts)
        if not normalized_hosts:
            raise ValueError("agent_browser_allowed_hosts_required")
        object.__setattr__(self, "allowed_hosts", normalized_hosts)
        return self


class AgentBrowserReadReceipt(BaseModel):
    contract: str = AGENT_BROWSER_RUNTIME_CONTRACT
    command_id: str
    application_id: str
    tenant_scope_ref: str
    auth_context_ref: str
    network_egress_boundary_ref: str
    session_name: str
    kind: AgentBrowserReadKind
    origin_shape: str
    output_char_count: int = Field(ge=0)
    content_boundary_present: bool
    pinned_tab: bool
    raw_content_retained: bool = False
    raw_url_query_retained: bool = False
    direct_execution_authorized: bool = False

    @model_validator(mode="after")
    def receipt_never_promotes_or_retains_page_secrets(self) -> "AgentBrowserReadReceipt":
        if self.raw_content_retained or self.raw_url_query_retained:
            raise ValueError("agent_browser_receipt_cannot_retain_page_content_or_query")
        if self.direct_execution_authorized:
            raise ValueError("agent_browser_read_receipt_never_authorizes_execution")
        if not self.content_boundary_present:
            raise ValueError("agent_browser_read_receipt_requires_content_boundary")
        if not self.pinned_tab:
            raise ValueError("agent_browser_read_receipt_requires_pinned_tab")
        return self


class AgentBrowserTransientRead(BaseModel):
    """Transient page material plus a safe serializable receipt.

    ``content`` is excluded from model serialization so ordinary evidence/audit
    serialization cannot accidentally persist page text or DOM material.
    Callers may use it in-memory for the current reasoning turn only.
    """

    content: str = Field(exclude=True)
    receipt: AgentBrowserReadReceipt
    content_must_not_be_persisted: bool = True


Runner = Callable[[list[str], float], Any]


def _default_runner(args: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=timeout_seconds,
    )


def _safe_origin_shape(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host:
        raise ValueError("agent_browser_https_origin_required")
    return urlunparse(("https", host, parsed.path or "/", "", "", ""))


def _host_allowed(url: str, allowed_hosts: frozenset[str]) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").casefold().rstrip(".") in allowed_hosts
    )


def _base_args(config: AgentBrowserCorporateSessionConfig) -> list[str]:
    parsed = urlparse(config.cdp_endpoint)
    args = [
        config.binary,
        "--session",
        config.session_name,
        "--cdp",
        str(parsed.port),
        "--pin-tab",
        "--content-boundaries",
        "--max-output",
        str(config.maximum_output_chars),
        "--action-policy",
        config.action_policy_path,
        "--json",
    ]
    return args


def _command_args(command: AgentBrowserReadCommand) -> list[str]:
    if command.kind is AgentBrowserReadKind.SNAPSHOT:
        return ["snapshot"]
    if command.kind is AgentBrowserReadKind.READ_ACTIVE:
        return ["read"]
    if command.kind is AgentBrowserReadKind.GET_URL:
        return ["get", "url"]
    if command.kind is AgentBrowserReadKind.GET_TEXT:
        return ["get", "text", command.selector or ""]
    raise ValueError("agent_browser_read_kind_unsupported")


def _extract_content(payload: dict[str, Any], kind: AgentBrowserReadKind) -> str:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("agent_browser_json_data_missing")
    if kind is AgentBrowserReadKind.SNAPSHOT:
        keys = ("snapshot", "text", "content")
    elif kind is AgentBrowserReadKind.READ_ACTIVE:
        keys = ("text", "markdown", "content", "snapshot")
    elif kind is AgentBrowserReadKind.GET_URL:
        keys = ("url", "text", "value")
    else:
        keys = ("text", "value", "content")
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    raise ValueError("agent_browser_expected_read_content_missing")


def _extract_origin(payload: dict[str, Any], content: str, kind: AgentBrowserReadKind) -> tuple[str, bool]:
    boundary = payload.get("_boundary")
    if isinstance(boundary, dict) and isinstance(boundary.get("origin"), str):
        return boundary["origin"], True
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("origin"), str):
        return data["origin"], False
    if kind is AgentBrowserReadKind.GET_URL:
        return content, False
    raise ValueError("agent_browser_content_boundary_origin_missing")


def execute_agent_browser_read(
    *,
    config: AgentBrowserCorporateSessionConfig,
    command: AgentBrowserReadCommand,
    runner: Runner = _default_runner,
) -> AgentBrowserTransientRead:
    """Execute one bounded semantic read against the pinned corporate tab."""

    args = [*_base_args(config), *_command_args(command)]
    try:
        completed = runner(args, command.timeout_seconds)
    except Exception as exc:
        raise RuntimeError(f"agent_browser_runner_error:{type(exc).__name__}") from None

    return_code = getattr(completed, "returncode", None)
    stdout = getattr(completed, "stdout", "")
    if return_code != 0:
        raise RuntimeError("agent_browser_command_failed")
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError):
        raise RuntimeError("agent_browser_invalid_json_output") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("agent_browser_unsuccessful_response")

    content = _extract_content(payload, command.kind)
    origin, boundary_present = _extract_origin(payload, content, command.kind)
    if not boundary_present and command.kind is not AgentBrowserReadKind.GET_URL:
        raise RuntimeError("agent_browser_content_boundary_missing")
    if not _host_allowed(origin, config.allowed_hosts):
        raise RuntimeError("agent_browser_observed_origin_not_allowlisted")

    receipt = AgentBrowserReadReceipt(
        command_id=command.command_id,
        application_id=config.application_id,
        tenant_scope_ref=config.tenant_scope_ref,
        auth_context_ref=config.auth_context_ref,
        network_egress_boundary_ref=config.network_egress_boundary_ref,
        session_name=config.session_name,
        kind=command.kind,
        origin_shape=_safe_origin_shape(origin),
        output_char_count=len(content),
        content_boundary_present=(boundary_present or command.kind is AgentBrowserReadKind.GET_URL),
        pinned_tab=config.pin_tab,
    )
    return AgentBrowserTransientRead(content=content, receipt=receipt)
