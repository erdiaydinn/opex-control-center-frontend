"""
EAY Phase 1 browser trust boundary.

Enforces:
- central bearer injection;
- memory-only OIDC user/token state;
- production-safe Workforce/Inventory persistence;
- SSO-authoritative production picker identity.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = (
    Path(__file__).resolve().parents[3]
)

SRC_ROOT = REPO_ROOT / "src"


def read(relative: str) -> str:
    return (
        REPO_ROOT / relative
    ).read_text(
        encoding="utf-8-sig"
    )


def test_bearer_auth_is_centralized():
    central_client = (
        SRC_ROOT
        / "api"
        / "client.js"
    ).resolve()

    violations = []

    for path in SRC_ROOT.rglob("*"):

        if (
            not path.is_file()
            or path.suffix
            not in {
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
            }
        ):
            continue

        source = path.read_text(
            encoding="utf-8-sig"
        )

        direct_auth = bool(
            re.search(
                r"Authorization\s*:",
                source,
            )
            or re.search(
                r"Bearer\s+\$\{",
                source,
            )
        )

        if (
            direct_auth
            and path.resolve()
            != central_client
        ):
            violations.append(
                str(
                    path.relative_to(
                        REPO_ROOT
                    )
                )
            )

    assert not violations, (
        "Direct bearer auth outside "
        "central API client: "
        + ", ".join(violations)
    )


def test_oidc_tokens_are_memory_only():
    source = read(
        "src/auth/oidcClient.js"
    )

    user_start = source.index(
        "userStore:"
    )

    state_start = source.index(
        "stateStore:"
    )

    user_block = source[
        user_start:state_start
    ]

    state_block = source[
        state_start:
    ]

    assert (
        "new InMemoryWebStorage()"
        in user_block
    )

    assert (
        "window.localStorage"
        not in user_block
    )

    assert (
        "window.sessionStorage"
        not in user_block
    )

    # PKCE redirect transaction state is allowed.
    assert (
        "window.sessionStorage"
        in state_block
    )

    assert (
        "store: window.localStorage"
        not in source
    )


def test_workforce_sensitive_storage_is_dev_only():
    source = read(
        "src/modules/workforce/"
        "workforceData.js"
    )

    assert (
        "function allowSensitivePilotStorage()"
        in source
    )

    assert (
        "import.meta.env.DEV"
        in source
    )

    assert (
        "purgeSensitiveWorkforceStorage"
        in source
    )

    assert (
        "localStorage.removeItem"
        in source
    )


def test_inventory_sensitive_storage_is_dev_only():
    source = read(
        "src/modules/inventory/"
        "InventoryDashboard.jsx"
    )

    assert (
        "function allowSensitivePilotStorage()"
        in source
    )

    assert (
        "import.meta.env.DEV"
        in source
    )

    assert (
        "purgeSensitiveInventoryStorage"
        in source
    )

    assert (
        "localStorage.removeItem"
        in source
    )


def test_picker_identity_is_sso_authoritative_in_production():
    source = read(
        "src/modules/workforce/"
        "WorkforcePickerApp.jsx"
    )

    start = source.index(
        "const currentPersonId"
    )

    context = source[
        start:start + 500
    ]

    assert (
        "user?.employeeId"
        in context
    )

    assert (
        "import.meta.env.DEV"
        in context
    )

    assert (
        "opex_picker_person_id"
        in context
    )

    assert (
        "LOCAL_PILOT_MODE"
        not in context
    )
