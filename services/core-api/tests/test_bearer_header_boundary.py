from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.core.security import (
    MAX_BEARER_TOKEN_CHARACTERS,
    _validated_bearer_token,
)


def make_request(*authorization_values: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/context",
            "headers": [
                (b"authorization", value.encode("latin-1"))
                for value in authorization_values
            ],
        }
    )


def credentials(token: str = "abc.def.ghi") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )


def assert_rejected(request: Request, supplied_credentials) -> None:
    try:
        _validated_bearer_token(
            request,
            supplied_credentials,
        )
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.headers == {"WWW-Authenticate": "Bearer"}
        return

    raise AssertionError("Bearer boundary unexpectedly accepted hostile input")


def test_single_unambiguous_bearer_header_is_accepted() -> None:
    token = "abc.def.ghi"
    assert _validated_bearer_token(
        make_request(f"Bearer {token}"),
        credentials(token),
    ) == token


def test_duplicate_authorization_headers_fail_closed() -> None:
    assert_rejected(
        make_request(
            "Bearer abc.def.ghi",
            "Bearer attacker.token.value",
        ),
        credentials(),
    )


def test_proxy_coalesced_authorization_header_fails_closed() -> None:
    assert_rejected(
        make_request(
            "Bearer abc.def.ghi,Bearer attacker.token.value"
        ),
        credentials(),
    )


def test_dependency_parser_disagreement_fails_closed() -> None:
    assert_rejected(
        make_request("Bearer abc.def.ghi"),
        credentials("different.token.value"),
    )


def test_whitespace_ambiguity_fails_closed() -> None:
    for raw_header in (
        " Bearer abc.def.ghi",
        "Bearer  abc.def.ghi",
        "Bearer\tabc.def.ghi",
        "Bearer abc.def.ghi ",
    ):
        assert_rejected(
            make_request(raw_header),
            credentials(),
        )


def test_control_character_in_token_fails_closed() -> None:
    assert_rejected(
        make_request("Bearer abc.def.ghi\x7f"),
        credentials("abc.def.ghi\x7f"),
    )


def test_oversized_bearer_token_fails_closed() -> None:
    token = "a" * (MAX_BEARER_TOKEN_CHARACTERS + 1)
    assert_rejected(
        make_request(f"Bearer {token}"),
        credentials(token),
    )


def test_direct_in_process_dependency_invocation_remains_supported() -> None:
    token = "abc.def.ghi"
    assert _validated_bearer_token(
        make_request(),
        credentials(token),
    ) == token


def test_missing_header_and_credentials_fail_closed() -> None:
    assert_rejected(
        make_request(),
        None,
    )
