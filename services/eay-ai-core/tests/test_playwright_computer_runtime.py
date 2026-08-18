import pytest

from app.playwright_computer_runtime import (
    BrowserAction,
    BrowserActionKind,
    BrowserLocator,
    LocatorKind,
    ManagedPlaywrightSession,
    PlaywrightSessionConfig,
)


class FakeRequest:
    method = "POST"
    url = "https://carsi.example.com/api/inventory/adjust?token=secret-token"
    resource_type = "fetch"
    post_data = '{"sku":"869123","quantity":3,"reason":"ZAYI"}'
    post_data_json = {"sku": "869123", "quantity": 3, "reason": "ZAYI"}

    def all_headers(self):
        return {
            "authorization": "Bearer top-secret",
            "cookie": "session=private",
            "content-type": "application/json",
        }

    def header_value(self, name):
        if name.casefold() == "content-type":
            return "application/json"
        return None


class FakeResponse:
    def __init__(self, url=None, resource_type="fetch"):
        self.request = FakeRequest()
        if url is not None:
            self.request.url = url
        self.request.resource_type = resource_type
        self.status = 200
        self.url = self.request.url

    def all_headers(self):
        return {
            "content-type": "application/json",
            "content-length": "64",
            "set-cookie": "session=new-private-value",
        }

    def json(self):
        return {"stock_on_hand": 24, "transaction_id": "TX-1"}


class FakeLocator:
    def __init__(self, page):
        self.page = page
        self.calls = []

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))
        self.page.emit_response(FakeResponse())
        self.page.emit_response(FakeResponse("https://telemetry.example.net/click"))

    def fill(self, value, **kwargs):
        self.calls.append(("fill", "<redacted>", kwargs))
        self.page.emit_response(FakeResponse())

    def press(self, key, **kwargs):
        self.calls.append(("press", key, kwargs))

    def select_option(self, value, **kwargs):
        self.calls.append(("select_option", "<redacted>", kwargs))


class FakePage:
    def __init__(self):
        self.url = "https://carsi.example.com/inventory?warehouse=fulya&token=browser-secret"
        self.handlers = []
        self.last_locator = None
        self.goto_calls = []

    def on(self, event, callback):
        assert event == "response"
        self.handlers.append(callback)

    def remove_listener(self, event, callback):
        assert event == "response"
        self.handlers.remove(callback)

    def emit_response(self, response):
        for handler in list(self.handlers):
            handler(response)

    def wait_for_timeout(self, milliseconds):
        assert milliseconds >= 0

    def get_by_role(self, role, **kwargs):
        assert role == "button"
        assert kwargs["name"] == "Stok Düş"
        self.last_locator = FakeLocator(self)
        return self.last_locator

    def get_by_label(self, value, **kwargs):
        self.last_locator = FakeLocator(self)
        return self.last_locator

    def get_by_text(self, value, **kwargs):
        self.last_locator = FakeLocator(self)
        return self.last_locator

    def get_by_placeholder(self, value, **kwargs):
        self.last_locator = FakeLocator(self)
        return self.last_locator

    def get_by_test_id(self, value):
        self.last_locator = FakeLocator(self)
        return self.last_locator

    def locator(self, value):
        self.last_locator = FakeLocator(self)
        return self.last_locator

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url


class FakeBrowser:
    def close(self):
        pass


class FakePlaywright:
    def stop(self):
        pass


def _config(**overrides):
    payload = dict(
        application_id="carsiportal",
        tenant_scope_ref="warehouse:fulya",
        auth_context_ref="managed-session:carsiportal",
        allowed_hosts=frozenset({"carsi.example.com"}),
    )
    payload.update(overrides)
    return PlaywrightSessionConfig(**payload)


def _session():
    page = FakePage()
    return ManagedPlaywrightSession(
        config=_config(),
        playwright=FakePlaywright(),
        browser=FakeBrowser(),
        context=object(),
        page=page,
    ), page


def test_remote_cdp_is_blocked_without_explicit_authorization():
    with pytest.raises(ValueError, match="playwright_remote_cdp_requires_explicit_authorization"):
        _config(cdp_endpoint="https://remote-debug.example.com:9222")


def test_navigation_is_exact_https_allowlisted():
    session, page = _session()
    session.goto("https://carsi.example.com/stock")
    assert page.goto_calls

    with pytest.raises(ValueError, match="playwright_navigation_host_not_allowlisted"):
        session.goto("https://evil.example.net/steal")

    with pytest.raises(ValueError, match="playwright_navigation_host_not_allowlisted"):
        session.goto("http://carsi.example.com/insecure")


def test_accessibility_first_action_captures_secret_free_api_observation():
    session, page = _session()
    receipt = session.perform(
        BrowserAction(
            action_id="stock-adjust-1",
            kind=BrowserActionKind.CLICK,
            locator=BrowserLocator(
                kind=LocatorKind.ROLE,
                value="button",
                accessible_name="Stok Düş",
            ),
            settle_ms=0,
        )
    )

    assert receipt.completed is True
    assert receipt.auth_context_ref == "managed-session:carsiportal"
    assert receipt.page_url_after == "https://carsi.example.com/inventory"
    assert "browser-secret" not in receipt.model_dump_json()
    assert receipt.input_value_retained is False
    assert receipt.direct_api_execution_authorized is False
    assert receipt.ignored_non_allowlisted_response_count == 1
    assert len(receipt.observations) == 1
    observation = receipt.observations[0]
    assert observation.raw_headers_retained is False
    assert observation.raw_payloads_retained is False
    assert observation.exchange.user_action_ref == "browser-action:stock-adjust-1"
    assert observation.exchange.authorization_header_present is True
    assert observation.exchange.cookie_header_present is True
    assert "secret-token" not in observation.exchange.url
    assert observation.request_schema is not None
    assert observation.response_schema is not None


def test_fill_value_never_appears_in_receipt():
    session, page = _session()
    secret_business_value = "8691234567890"
    receipt = session.perform(
        BrowserAction(
            action_id="fill-barcode",
            kind=BrowserActionKind.FILL,
            locator=BrowserLocator(kind=LocatorKind.LABEL, value="Barkod"),
            input_value=secret_business_value,
            settle_ms=0,
        )
    )

    assert receipt.input_value_retained is False
    assert secret_business_value not in receipt.model_dump_json()


def test_role_locator_requires_accessible_name():
    with pytest.raises(ValueError, match="playwright_role_locator_requires_accessible_name"):
        BrowserLocator(kind=LocatorKind.ROLE, value="button")
