from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from app.platform_tool_authorizer import (
    AUTHORIZATION_PATH,
    JARVIS_SERVICE_ASSERTION_HEADER,
    PlatformToolAuthorizationContractError,
    PlatformToolAuthorizationDenied,
    PlatformToolAuthorizationIndeterminate,
    PlatformToolAuthorizer,
    PlatformToolAuthorizerSettings,
)
from app.tool_contracts import ToolPlan


class RecordingSigner:
    def __init__(self) -> None:
        self.calls = 0

    def issue_tool_execution_assertion(self) -> str:
        self.calls += 1
        return f"machine-assertion-{self.calls}"


def plan() -> ToolPlan:
    return ToolPlan(
        tool="ops_kpi_query",
        query_id="ops.orders.v1",
        required_scope=["ops:read"],
        arguments={
            "metric": "orders",
            "start_date": "2026-08-01",
            "end_date": "2026-08-12",
            "stores": [],
            "limit": 50,
        },
        read_only=True,
        model_authored_sql_allowed=False,
        requires_human_review=False,
    )


def arguments_hash(arguments: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def reason_hash(reason: str) -> str:
    return hashlib.sha256(
        " ".join(reason.split()).encode("utf-8")
    ).hexdigest()


def success_response(*, reason: str = "read current orders") -> dict:
    tool_plan = plan()
    return {
        "request_id": "request-1",
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "actor_subject": "user-1",
        "tool": tool_plan.tool,
        "granted_scopes": ["ops:read"],
        "authorization_fingerprint": "a" * 64,
        "arguments_sha256": arguments_hash(tool_plan.arguments),
        "reason_sha256": reason_hash(reason),
    }


@pytest.mark.asyncio
async def test_authorizer_sends_only_opaque_grant_and_exact_invocation() -> None:
    signer = RecordingSigner()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["assertion"] = request.headers[
            JARVIS_SERVICE_ASSERTION_HEADER
        ]
        body = json.loads(request.content)
        seen["body"] = body
        return httpx.Response(
            200,
            json=success_response(),
        )

    async with httpx.AsyncClient(
        base_url="http://core-api:8000",
        transport=httpx.MockTransport(handler),
    ) as client:
        authorizer = PlatformToolAuthorizer(
            PlatformToolAuthorizerSettings(
                base_url="http://core-api:8000"
            ),
            signer,  # type: ignore[arg-type]
            client=client,
        )
        context = await authorizer.authorize(
            grant_token="g" * 43,
            plan=plan(),
            reason="read current orders",
        )

    assert seen["path"] == AUTHORIZATION_PATH
    assert seen["assertion"] == "machine-assertion-1"
    assert signer.calls == 1

    body = seen["body"]
    assert isinstance(body, dict)
    assert set(body) == {
        "grant_token",
        "tool",
        "arguments",
        "reason",
    }
    assert "tenant_id" not in body
    assert "actor_subject" not in body
    assert "permissions" not in body
    assert "granted_scopes" not in body

    assert context.tenant_id.hex == "11111111111141118111111111111111"
    assert context.actor_subject == "user-1"
    assert context.granted_scopes == ("ops:read",)


@pytest.mark.asyncio
async def test_transport_failure_is_indeterminate_and_never_retried() -> None:
    signer = RecordingSigner()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError(
            "network failure",
            request=request,
        )

    async with httpx.AsyncClient(
        base_url="http://core-api:8000",
        transport=httpx.MockTransport(handler),
    ) as client:
        authorizer = PlatformToolAuthorizer(
            PlatformToolAuthorizerSettings(
                base_url="http://core-api:8000"
            ),
            signer,  # type: ignore[arg-type]
            client=client,
        )

        with pytest.raises(
            PlatformToolAuthorizationIndeterminate
        ):
            await authorizer.authorize(
                grant_token="g" * 43,
                plan=plan(),
                reason="read current orders",
            )

    assert calls == 1
    assert signer.calls == 1


@pytest.mark.asyncio
async def test_503_is_indeterminate_and_never_retried() -> None:
    signer = RecordingSigner()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            503,
            json={"detail": "audit unavailable"},
        )

    async with httpx.AsyncClient(
        base_url="http://core-api:8000",
        transport=httpx.MockTransport(handler),
    ) as client:
        authorizer = PlatformToolAuthorizer(
            PlatformToolAuthorizerSettings(
                base_url="http://core-api:8000"
            ),
            signer,  # type: ignore[arg-type]
            client=client,
        )

        with pytest.raises(
            PlatformToolAuthorizationIndeterminate
        ):
            await authorizer.authorize(
                grant_token="g" * 43,
                plan=plan(),
                reason="read current orders",
            )

    assert calls == 1
    assert signer.calls == 1


@pytest.mark.asyncio
async def test_401_is_terminal_denial_without_retry() -> None:
    signer = RecordingSigner()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(
        base_url="http://core-api:8000",
        transport=httpx.MockTransport(handler),
    ) as client:
        authorizer = PlatformToolAuthorizer(
            PlatformToolAuthorizerSettings(
                base_url="http://core-api:8000"
            ),
            signer,  # type: ignore[arg-type]
            client=client,
        )

        with pytest.raises(
            PlatformToolAuthorizationDenied
        ):
            await authorizer.authorize(
                grant_token="g" * 43,
                plan=plan(),
                reason="read current orders",
            )

    assert calls == 1
    assert signer.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        {"tool": "catalog_query"},
        {"granted_scopes": ["ops:read", "legal:read"]},
        {"arguments_sha256": "b" * 64},
        {"reason_sha256": "c" * 64},
        {"tenant_id": "not-a-uuid"},
        {"unexpected": "field"},
    ],
)
async def test_response_contract_tampering_is_rejected(
    mutation: dict[str, object],
) -> None:
    payload = success_response()
    payload.update(mutation)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        base_url="http://core-api:8000",
        transport=httpx.MockTransport(handler),
    ) as client:
        authorizer = PlatformToolAuthorizer(
            PlatformToolAuthorizerSettings(
                base_url="http://core-api:8000"
            ),
            RecordingSigner(),  # type: ignore[arg-type]
            client=client,
        )

        with pytest.raises(
            PlatformToolAuthorizationContractError
        ):
            await authorizer.authorize(
                grant_token="g" * 43,
                plan=plan(),
                reason="read current orders",
            )


def test_unsafe_tool_plan_is_rejected_before_network() -> None:
    unsafe = plan().model_copy(
        update={
            "read_only": False,
        }
    )
    authorizer = PlatformToolAuthorizer(
        PlatformToolAuthorizerSettings(
            base_url="http://core-api:8000"
        ),
        RecordingSigner(),  # type: ignore[arg-type]
    )

    async def run() -> None:
        with pytest.raises(
            PlatformToolAuthorizationContractError
        ):
            await authorizer.authorize(
                grant_token="g" * 43,
                plan=unsafe,
                reason="read current orders",
            )

    import asyncio

    asyncio.run(run())
