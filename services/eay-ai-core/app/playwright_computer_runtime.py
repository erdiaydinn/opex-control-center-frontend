"""Live Playwright computer-use runtime for authorized managed browser sessions.

This is the concrete browser executor behind Jarvis' computer-learning stack.
It can attach to an existing Chromium session over local CDP, execute bounded
DOM actions with accessibility-first locators, and capture allowlisted XHR/fetch
traffic. Raw cookies, bearer tokens, payload values and page query parameters
never enter returned receipts.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, model_validator

from .api_discovery_intelligence import CaptureSource
from .browser_api_observer import BrowserApiObservation, observe_browser_exchange

PLAYWRIGHT_COMPUTER_RUNTIME_CONTRACT = "eay-playwright-computer-runtime-v1"


class LocatorKind(str, Enum):
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    PLACEHOLDER = "placeholder"
    TEST_ID = "test_id"
    CSS = "css"


class BrowserActionKind(str, Enum):
    CLICK = "click"
    FILL = "fill"
    PRESS = "press"
    SELECT_OPTION = "select_option"


class BrowserLocator(BaseModel):
    kind: LocatorKind
    value: str = Field(min_length=1)
    accessible_name: str | None = None
    exact: bool = True

    @model_validator(mode="after")
    def role_requires_accessible_name(self) -> "BrowserLocator":
        if self.kind is LocatorKind.ROLE and not self.accessible_name:
            raise ValueError("playwright_role_locator_requires_accessible_name")
        return self


class BrowserAction(BaseModel):
    action_id: str = Field(min_length=1)
    kind: BrowserActionKind
    locator: BrowserLocator
    input_value: str | None = None
    key: str | None = None
    timeout_ms: int = Field(default=15000, ge=100, le=60000)
    settle_ms: int = Field(default=750, ge=0, le=10000)

    @model_validator(mode="after")
    def action_payload_matches_kind(self) -> "BrowserAction":
        if self.kind in {BrowserActionKind.FILL, BrowserActionKind.SELECT_OPTION} and self.input_value is None:
            raise ValueError("playwright_action_input_value_required")
        if self.kind is BrowserActionKind.PRESS and not self.key:
            raise ValueError("playwright_action_key_required")
        return self


class PlaywrightSessionConfig(BaseModel):
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    auth_context_ref: str = Field(min_length=1)
    allowed_hosts: frozenset[str] = Field(min_length=1)
    cdp_endpoint: str = "http://127.0.0.1:9222"
    allow_remote_cdp: bool = False
    maximum_json_bytes: int = Field(default=131072, ge=1024, le=1048576)

    @model_validator(mode="after")
    def validate_cdp_boundary(self) -> "PlaywrightSessionConfig":
        parsed = urlparse(self.cdp_endpoint)
        if parsed.scheme not in {"http", "https", "ws", "wss"}:
            raise ValueError("playwright_cdp_scheme_not_allowed")
        host = (parsed.hostname or "").casefold()
        if not host:
            raise ValueError("playwright_cdp_host_required")
        if not self.allow_remote_cdp and host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("playwright_remote_cdp_requires_explicit_authorization")
        normalized_hosts = {item.casefold().rstrip(".") for item in self.allowed_hosts}
        if not normalized_hosts:
            raise ValueError("playwright_allowed_hosts_required")
        object.__setattr__(self, "allowed_hosts", frozenset(normalized_hosts))
        return self


class BrowserActionReceipt(BaseModel):
    contract: str = PLAYWRIGHT_COMPUTER_RUNTIME_CONTRACT
    action_id: str
    application_id: str
    tenant_scope_ref: str
    auth_context_ref: str = Field(min_length=1)
    locator_kind: LocatorKind
    action_kind: BrowserActionKind
    input_value_retained: bool = False
    completed: bool
    page_url_after: str | None = None
    observations: tuple[BrowserApiObservation, ...] = ()
    ignored_non_allowlisted_response_count: int = Field(default=0, ge=0)
    capture_errors: tuple[str, ...] = ()
    direct_api_execution_authorized: bool = False

    @model_validator(mode="after")
    def runtime_receipt_preserves_boundaries(self) -> "BrowserActionReceipt":
        if self.input_value_retained:
            raise ValueError("playwright_runtime_must_not_retain_action_input_value")
        if self.direct_api_execution_authorized:
            raise ValueError("playwright_runtime_never_authorizes_direct_api_execution")
        if self.page_url_after:
            parsed = urlparse(self.page_url_after)
            if parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ValueError("playwright_receipt_page_url_must_be_sanitized")
        return self


def _host_is_allowed(url: str, allowed_hosts: frozenset[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").casefold().rstrip(".") in allowed_hosts


def _sanitized_page_url(url: str | None) -> str | None:
    if not url or url == "about:blank":
        return url
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.casefold().rstrip(".")
    if parsed.port and parsed.port != 443:
        netloc = f"{host}:{parsed.port}"
    else:
        netloc = host
    return urlunparse(("https", netloc, parsed.path or "/", "", "", ""))


def _content_type(headers: dict[str, str]) -> str | None:
    for key, value in headers.items():
        if key.casefold() == "content-type":
            return value
    return None


def _content_length(headers: dict[str, str]) -> int | None:
    for key, value in headers.items():
        if key.casefold() == "content-length":
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _safe_request_payload(request: Any, maximum_json_bytes: int) -> Any:
    content_type = (request.header_value("content-type") or "").casefold()
    if "json" not in content_type and "graphql" not in content_type:
        return None
    post_data = request.post_data
    if post_data is None or len(post_data.encode("utf-8")) > maximum_json_bytes:
        return None
    try:
        return request.post_data_json
    except Exception:
        try:
            return json.loads(post_data)
        except Exception:
            return None


def _safe_response_payload(response: Any, headers: dict[str, str], maximum_json_bytes: int) -> Any:
    content_type = (_content_type(headers) or "").casefold()
    if "json" not in content_type and "graphql" not in content_type:
        return None
    content_length = _content_length(headers)
    if content_length is None or content_length > maximum_json_bytes:
        return None
    try:
        return response.json()
    except Exception:
        return None


def _resolve_locator(page: Any, locator: BrowserLocator) -> Any:
    if locator.kind is LocatorKind.ROLE:
        return page.get_by_role(locator.value, name=locator.accessible_name, exact=locator.exact)
    if locator.kind is LocatorKind.LABEL:
        return page.get_by_label(locator.value, exact=locator.exact)
    if locator.kind is LocatorKind.TEXT:
        return page.get_by_text(locator.value, exact=locator.exact)
    if locator.kind is LocatorKind.PLACEHOLDER:
        return page.get_by_placeholder(locator.value, exact=locator.exact)
    if locator.kind is LocatorKind.TEST_ID:
        return page.get_by_test_id(locator.value)
    return page.locator(locator.value)


def _execute_action(page: Any, action: BrowserAction) -> None:
    locator = _resolve_locator(page, action.locator)
    if action.kind is BrowserActionKind.CLICK:
        locator.click(timeout=action.timeout_ms)
    elif action.kind is BrowserActionKind.FILL:
        locator.fill(action.input_value, timeout=action.timeout_ms)
    elif action.kind is BrowserActionKind.PRESS:
        locator.press(action.key, timeout=action.timeout_ms)
    elif action.kind is BrowserActionKind.SELECT_OPTION:
        locator.select_option(action.input_value, timeout=action.timeout_ms)
    else:  # pragma: no cover
        raise ValueError("playwright_action_kind_unsupported")


def _capture_response(
    response: Any,
    *,
    config: PlaywrightSessionConfig,
    action_ref: str,
) -> BrowserApiObservation:
    request = response.request
    request_headers = request.all_headers()
    response_headers = response.all_headers()
    return observe_browser_exchange(
        application_id=config.application_id,
        capture_source=CaptureSource.PLAYWRIGHT_NETWORK,
        method=request.method,
        url=request.url,
        status_code=response.status,
        allowed_hosts=set(config.allowed_hosts),
        resource_type=request.resource_type,
        request_headers=request_headers,
        response_headers=response_headers,
        request_content_type=_content_type(request_headers),
        response_content_type=_content_type(response_headers),
        request_payload=_safe_request_payload(request, config.maximum_json_bytes),
        response_payload=_safe_response_payload(response, response_headers, config.maximum_json_bytes),
        user_action_ref=action_ref,
        auth_context_ref=config.auth_context_ref,
        tenant_scope_ref=config.tenant_scope_ref,
    )


class ManagedPlaywrightSession:
    """Synchronous managed browser session; callers own higher-level policy gates."""

    def __init__(self, *, config: PlaywrightSessionConfig, playwright: Any, browser: Any, context: Any, page: Any):
        self.config = config
        self._playwright = playwright
        self._browser = browser
        self._context = context
        self._page = page

    @classmethod
    def connect(cls, config: PlaywrightSessionConfig) -> "ManagedPlaywrightSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("playwright_optional_dependency_not_installed") from exc

        manager = sync_playwright().start()
        try:
            browser = manager.chromium.connect_over_cdp(config.cdp_endpoint)
            if not browser.contexts:
                raise RuntimeError("playwright_managed_browser_context_missing")
            context = browser.contexts[0]
            if not context.pages:
                raise RuntimeError("playwright_managed_browser_page_missing")
            page = context.pages[0]
            if page.url and page.url != "about:blank" and not _host_is_allowed(page.url, config.allowed_hosts):
                raise RuntimeError("playwright_existing_page_host_not_allowlisted")
            return cls(config=config, playwright=manager, browser=browser, context=context, page=page)
        except Exception:
            manager.stop()
            raise

    def goto(self, url: str, *, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> None:
        if not _host_is_allowed(url, self.config.allowed_hosts):
            raise ValueError("playwright_navigation_host_not_allowlisted")
        self._page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        if not _host_is_allowed(self._page.url, self.config.allowed_hosts):
            raise RuntimeError("playwright_navigation_redirected_outside_allowlist")

    def perform(self, action: BrowserAction) -> BrowserActionReceipt:
        observations: list[BrowserApiObservation] = []
        capture_errors: list[str] = []
        ignored = 0
        action_ref = f"browser-action:{action.action_id}"
        active = True

        def on_response(response: Any) -> None:
            nonlocal ignored
            if not active:
                return
            if not _host_is_allowed(response.url, self.config.allowed_hosts):
                ignored += 1
                return
            request_type = getattr(response.request, "resource_type", "")
            if str(request_type).casefold() not in {"xhr", "fetch"}:
                return
            try:
                observations.append(_capture_response(response, config=self.config, action_ref=action_ref))
            except Exception as exc:
                capture_errors.append(type(exc).__name__)

        self._page.on("response", on_response)
        completed = False
        try:
            _execute_action(self._page, action)
            if action.settle_ms:
                self._page.wait_for_timeout(action.settle_ms)
            completed = True
        finally:
            active = False
            try:
                self._page.remove_listener("response", on_response)
            except Exception:
                pass

        raw_page_url_after = self._page.url
        if raw_page_url_after and raw_page_url_after != "about:blank" and not _host_is_allowed(raw_page_url_after, self.config.allowed_hosts):
            raise RuntimeError("playwright_action_navigated_outside_allowlist")
        return BrowserActionReceipt(
            action_id=action.action_id,
            application_id=self.config.application_id,
            tenant_scope_ref=self.config.tenant_scope_ref,
            auth_context_ref=self.config.auth_context_ref,
            locator_kind=action.locator.kind,
            action_kind=action.kind,
            completed=completed,
            page_url_after=_sanitized_page_url(raw_page_url_after),
            observations=tuple(observations),
            ignored_non_allowlisted_response_count=ignored,
            capture_errors=tuple(capture_errors),
        )

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._playwright.stop()

    def __enter__(self) -> "ManagedPlaywrightSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
