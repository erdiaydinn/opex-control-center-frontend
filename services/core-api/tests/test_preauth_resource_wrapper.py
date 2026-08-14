"""Contract tests for the Core pre-auth database wrapper."""

import asyncio

import pytest

import app.core.resources as resources

SAFE_FIELDS = {
    "tenant_id",
    "tenant_slug",
    "provider_id",
    "provider_key",
    "protocol",
    "provider_display_name",
    "issuer",
    "client_id",
    "audiences",
    "scopes",
    "allowed_algorithms",
}


class FakeResult:
    def __init__(
        self,
        rows,
    ):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeConnection:
    def __init__(
        self,
        rows,
    ):
        self.rows = rows
        self.calls = []

    async def execute(
        self,
        statement,
        parameters,
    ):
        self.calls.append(
            (
                str(statement),
                dict(parameters),
            )
        )

        return FakeResult(
            self.rows
        )


class FakeConnectionContext:
    def __init__(
        self,
        connection,
    ):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False


class FakeEngine:
    def __init__(
        self,
        connection,
    ):
        self.connection = connection

    def connect(self):
        return FakeConnectionContext(
            self.connection
        )


def run(
    coroutine,
):
    return asyncio.run(
        coroutine
    )


def test_wrapper_uses_only_security_definer_function(
    monkeypatch,
) -> None:
    connection = FakeConnection(
        [
            {
                "tenant_id":
                    "00000000-0000-0000-0000-00000000ab01",
                "tenant_slug":
                    "tenant-a",
                "provider_id":
                    "00000000-0000-0000-0000-00000000ab11",
                "provider_key":
                    "primary",
                "protocol":
                    "oidc",
                "provider_display_name":
                    "Primary OIDC",
                "issuer":
                    "https://idp.example.test",
                "client_id":
                    "opex-client",
                "audiences":
                    ["opex-core-api"],
                "scopes":
                    ["openid", "profile"],
                "allowed_algorithms":
                    ["ES256"],
            }
        ]
    )

    monkeypatch.setattr(
        resources,
        "engine",
        FakeEngine(
            connection
        ),
    )

    items = run(
        resources.resolve_preauth_oidc_providers(
            hostname="tenant.example.test"
        )
    )

    assert len(items) == 1

    assert (
        set(items[0])
        == SAFE_FIELDS
    )

    assert len(
        connection.calls
    ) == 1

    sql, parameters = (
        connection.calls[0]
    )

    normalized_sql = " ".join(
        sql.lower().split()
    )

    assert (
        "public.resolve_preauth_oidc_providers"
        in normalized_sql
    )

    for forbidden_relation in (
        " from tenants ",
        " from tenant_domains ",
        " from identity_providers ",
        " from oidc_provider_configs ",
        " join tenants ",
        " join tenant_domains ",
        " join identity_providers ",
        " join oidc_provider_configs ",
    ):
        assert (
            forbidden_relation
            not in (
                " "
                + normalized_sql
                + " "
            )
        )

    assert parameters == {
        "hostname":
            "tenant.example.test"
    }


def test_wrapper_does_not_expose_secret_or_authority_fields(
    monkeypatch,
) -> None:
    connection = FakeConnection(
        [
            {
                "tenant_id":
                    "00000000-0000-0000-0000-00000000ab01",
                "tenant_slug":
                    "tenant-a",
                "provider_id":
                    "00000000-0000-0000-0000-00000000ab11",
                "provider_key":
                    "primary",
                "protocol":
                    "oidc",
                "provider_display_name":
                    "Primary OIDC",
                "issuer":
                    "https://idp.example.test",
                "client_id":
                    "opex-client",
                "audiences":
                    [],
                "scopes":
                    ["openid"],
                "allowed_algorithms":
                    ["ES256"],

                # Simulate extra attacker-interesting columns
                # appearing in a driver/result implementation.
                "credential_ref":
                    "SECRET-CANARY",
                "token_endpoint_auth_method":
                    "client_secret_basic",
                "roles":
                    ["super_admin"],
                "permissions":
                    ["*"],
            }
        ]
    )

    monkeypatch.setattr(
        resources,
        "engine",
        FakeEngine(
            connection
        ),
    )

    item = run(
        resources.resolve_preauth_oidc_providers(
            hostname="tenant.example.test"
        )
    )[0]

    assert (
        set(item)
        == SAFE_FIELDS
    )

    serialized = repr(
        item
    )

    assert (
        "SECRET-CANARY"
        not in serialized
    )

    for forbidden in (
        "credential_ref",
        "token_endpoint_auth_method",
        "roles",
        "permissions",
    ):
        assert (
            forbidden
            not in item
        )


@pytest.mark.parametrize(
    "hostname",
    [
        "",
        " Tenant.example.test",
        "tenant.example.test ",
        "TENANT.example.test",
        ".tenant.example.test",
        "tenant.example.test.",
        "tenant..example.test",
        "tenant/example.test",
        "tenant@example.test",
        "t?nant.example.test",
    ],
)
def test_wrapper_rejects_noncanonical_hostname_before_database(
    monkeypatch,
    hostname,
) -> None:
    connection = FakeConnection(
        []
    )

    monkeypatch.setattr(
        resources,
        "engine",
        FakeEngine(
            connection
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "Pre-auth hostname is invalid"
        ),
    ):
        run(
            resources.resolve_preauth_oidc_providers(
                hostname=hostname
            )
        )

    assert (
        connection.calls
        == []
    )


def test_wrapper_accepts_punycode_ascii_hostname(
    monkeypatch,
) -> None:
    connection = FakeConnection(
        []
    )

    monkeypatch.setattr(
        resources,
        "engine",
        FakeEngine(
            connection
        ),
    )

    result = run(
        resources.resolve_preauth_oidc_providers(
            hostname=(
                "xn--rnek-4qa.example.test"
            )
        )
    )

    assert result == ()

    assert len(
        connection.calls
    ) == 1
