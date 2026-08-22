import json
from types import SimpleNamespace

import pytest

from app.agent_browser_runtime import (
    AgentBrowserCorporateSessionConfig,
    AgentBrowserReadCommand,
    AgentBrowserReadKind,
    execute_agent_browser_read,
)


HOST = "carsi-portal.yemeksepeti.com"


def _config(**overrides):
    payload = dict(
        application_id="yemeksepeti-carsi-portal",
        tenant_scope_ref="tenant://YS_TR",
        auth_context_ref="auth://managed-okta-session",
        network_egress_boundary_ref="egress://managed-corporate-browser/ys-tr",
        allowed_hosts=frozenset({HOST}),
        session_name="eay-carsi-read",
        cdp_endpoint="http://127.0.0.1:9222",
    )
    payload.update(overrides)
    return AgentBrowserCorporateSessionConfig(**payload)


def _runner(payload, seen):
    def run(args, timeout):
        seen.append((args, timeout))
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    return run


def test_snapshot_is_pinned_bounded_and_page_content_is_transient_only():
    sensitive = "Fulya barcode 8691234567890 stock 27"
    seen = []
    result = execute_agent_browser_read(
        config=_config(),
        command=AgentBrowserReadCommand(command_id="snapshot-1", kind=AgentBrowserReadKind.SNAPSHOT),
        runner=_runner(
            {
                "success": True,
                "data": {"snapshot": sensitive},
                "_boundary": {
                    "nonce": "abc123",
                    "origin": f"https://{HOST}/tr/inventory?token=must-not-retain",
                },
            },
            seen,
        ),
    )

    assert result.content == sensitive
    serialized = result.model_dump_json()
    assert sensitive not in serialized
    assert "8691234567890" not in serialized
    assert "must-not-retain" not in serialized
    assert result.receipt.origin_shape == f"https://{HOST}/tr/inventory"
    assert result.receipt.direct_execution_authorized is False
    args = seen[0][0]
    assert "--session" in args
    assert "eay-carsi-read" in args
    assert "--pin-tab" in args
    assert "--content-boundaries" in args
    assert "--action-policy" in args
    assert "--allowed-domains" not in args
    assert args[-1] == "snapshot"


def test_corporate_attach_requires_loopback_pin_content_boundaries_and_egress_reference():
    with pytest.raises(ValueError, match="agent_browser_remote_cdp_requires_explicit_authorization"):
        _config(cdp_endpoint="https://remote-debug.example.com:9222")
    with pytest.raises(ValueError, match="agent_browser_corporate_session_requires_pin_tab"):
        _config(pin_tab=False)
    with pytest.raises(ValueError, match="agent_browser_corporate_session_requires_content_boundaries"):
        _config(content_boundaries=False)
    with pytest.raises(ValueError, match="agent_browser_corporate_session_requires_egress_boundary_ref"):
        _config(network_egress_boundary_ref=" ")


def test_non_allowlisted_observed_origin_fails_closed():
    with pytest.raises(RuntimeError, match="agent_browser_observed_origin_not_allowlisted"):
        execute_agent_browser_read(
            config=_config(),
            command=AgentBrowserReadCommand(command_id="snapshot-evil", kind=AgentBrowserReadKind.SNAPSHOT),
            runner=_runner(
                {
                    "success": True,
                    "data": {"snapshot": "untrusted"},
                    "_boundary": {"nonce": "n", "origin": "https://evil.example.net/steal"},
                },
                [],
            ),
        )


def test_snapshot_without_content_boundary_is_rejected():
    with pytest.raises(RuntimeError, match="agent_browser_content_boundary_missing"):
        execute_agent_browser_read(
            config=_config(),
            command=AgentBrowserReadCommand(command_id="snapshot-no-boundary", kind=AgentBrowserReadKind.SNAPSHOT),
            runner=_runner(
                {
                    "success": True,
                    "data": {"snapshot": "page text", "origin": f"https://{HOST}/tr/"},
                },
                [],
            ),
        )


def test_get_url_keeps_raw_query_transient_but_receipt_is_query_free():
    raw_url = f"https://{HOST}/tr/orders?warehouse=fulya&secret=otp"
    result = execute_agent_browser_read(
        config=_config(),
        command=AgentBrowserReadCommand(command_id="url-1", kind=AgentBrowserReadKind.GET_URL),
        runner=_runner({"success": True, "data": {"url": raw_url}}, []),
    )

    assert result.content == raw_url
    assert result.receipt.origin_shape == f"https://{HOST}/tr/orders"
    assert "secret=otp" not in result.model_dump_json()


def test_cli_failure_is_sanitized_and_does_not_retain_stderr():
    def runner(args, timeout):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Bearer secret-token password=private",
        )

    with pytest.raises(RuntimeError, match="^agent_browser_command_failed$") as exc:
        execute_agent_browser_read(
            config=_config(),
            command=AgentBrowserReadCommand(command_id="fail", kind=AgentBrowserReadKind.SNAPSHOT),
            runner=runner,
        )
    assert "secret-token" not in str(exc.value)
