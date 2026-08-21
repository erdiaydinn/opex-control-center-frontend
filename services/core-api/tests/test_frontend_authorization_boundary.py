from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = REPO_ROOT / "src"


def _read(relative: str) -> str:
    return (
        FRONTEND_ROOT / relative
    ).read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def _frontend_sources():
    for path in FRONTEND_ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix
            in {".js", ".jsx", ".ts", ".tsx"}
        ):
            yield path


def test_legacy_access_config_is_deleted() -> None:
    assert not (
        FRONTEND_ROOT /
        "auth/accessConfig.js"
    ).exists()


def test_no_persistent_access_token_storage() -> None:
    forbidden = (
        "opex_access_token",
        "opex_session_token",
    )

    for path in _frontend_sources():
        text = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        for needle in forbidden:
            assert needle not in text, (
                f"{needle} reintroduced in "
                f"{path.relative_to(REPO_ROOT)}"
            )


def test_token_store_is_memory_only() -> None:
    text = _read("auth/tokenStore.js")

    assert "localStorage" not in text
    assert "sessionStorage" not in text
    assert "document.cookie" not in text
    assert "window." not in text


def test_oidc_uses_code_flow_and_memory_user_store() -> None:
    text = _read("auth/oidcClient.js")

    assert 'response_type: "code"' in text
    assert "InMemoryWebStorage" in text
    assert "automaticSilentRenew: true" in text
    assert "revokeTokensOnSignout: true" in text

    # sessionStorage is allowed only for OIDC
    # transient PKCE/state correlation.
    assert (
        "new WebStorageStateStore"
        in text
    )


def test_frontend_cannot_generate_dev_tokens() -> None:
    text = _read("auth/AuthContext.jsx")

    assert "dev.${" not in text
    assert '"dev."' not in text
    assert "'dev.'" not in text
    assert "buildUserFromEmail" not in text
    assert "DEFAULT_ACCESS_CONFIG" not in text


def test_api_identity_is_bearer_only() -> None:
    text = _read("api/client.js")

    # Authentication must be centralized and callers may not supply or
    # override a browser-authored identity. Do not bind this security contract
    # to source whitespace/line wrapping.
    assert "function requireAccessToken()" in text
    assert "const token = getAccessToken();" in text
    assert "if (!token) throw new ApiError" in text
    assert (
        'headers.set("Authorization", '
        '`Bearer ${requireAccessToken()}`);'
        in text
    )

    for header in (
        "X-User-Email",
        "X-OPEX-User",
        "X-OPEX-Role",
    ):
        assert (
            f'headers.delete("{header}")'
            in text
        )

        assert (
            f'headers.set("{header}"'
            not in text
        )

    # Candidate/public capability calls must never inherit employee bearer or
    # cookie identity. This keeps anonymous recruitment links isolated from an
    # employee session even when both are open in the same browser.
    assert "function buildPublicHeaders(options = {})" in text
    assert 'headers.delete("Authorization")' in text
    assert 'headers.delete("Cookie")' in text
    assert 'credentials: "omit"' in text
    assert 'referrerPolicy: "no-referrer"' in text


def test_protected_route_has_no_role_bypass() -> None:
    text = _read("auth/ProtectedRoute.jsx")

    assert "isSuperAdmin" not in text
    assert "can(moduleKey, action)" in text


def test_oidc_callback_route_exists() -> None:
    app = _read("App.jsx")

    assert 'path="/auth/callback"' in app
    assert "<AuthCallback />" in app


def test_login_has_no_local_password_authority() -> None:
    text = _read("pages/Login.jsx")

    assert 'type="password"' not in text
    assert "demoUsers" not in text
    assert "DEFAULT_USERS" not in text
    assert "opex_remember_user" not in text
    assert "login({" in text


def test_planogram_does_not_read_persistent_tokens() -> None:
    text = _read(
        "modules/planogram/"
        "PlanogramStudio.jsx"
    )

    # Non-sensitive UI preferences such as theme may use
    # localStorage. Authentication material may not.
    forbidden_auth_storage = (
        "opex_access_token",
        "opex_session_token",
        "getOpexAccessToken",
    )

    for needle in forbidden_auth_storage:
        assert needle not in text

    # Phase 1 quarantine is stricter than the previous
    # memory-only token contract: Planogram must have no
    # access-token capability at all.
    assert "getAccessToken" not in text
    assert "accessToken" not in text
    assert "postMessage" not in text


def test_dockos_has_no_local_identity_authority() -> None:
    text = _read(
        "modules/DockOS/"
        "dockosPermissions.js"
    )

    forbidden = (
        "accessConfig",
        "ADMIN_EMAILS",
        "getSessionUser",
        "canUserFeature",
        "canUserAction",
        "getUserModuleScope",
        "isSupplierUser",
        "isAdminUser",
    )

    for needle in forbidden:
        assert needle not in text


def test_dockos_unknown_permissions_fail_closed() -> None:
    text = _read(
        "modules/DockOS/"
        "dockosPermissions.js"
    )

    assert (
        "Object.values(DOCKOS_FEATURES)"
        in text
    )
    assert (
        "Object.values(DOCKOS_ACTIONS)"
        in text
    )
    assert (
        "`feature:dockos:${featureKey}`"
        in text
    )
    assert (
        "`action:dockos:${actionKey}`"
        in text
    )


def test_dockos_never_bypasses_gateway() -> None:
    text = _read(
        "modules/DockOS/dockosApi.js"
    )

    assert ":8000" not in text
    assert "127.0.0.1" not in text
    assert "LOCAL_API_ORIGIN" not in text
    assert "X-OPEX-User" not in text
    assert "X-OPEX-Role" not in text
    assert "scope_type" not in text

    assert (
        "authenticatedApiFetch"
        in text
    )


def test_browser_cannot_authorize_dockos_scope() -> None:
    text = _read(
        "modules/DockOS/dockosApi.js"
    )

    # Browser may send ordinary business filters,
    # but not an authorization scope claim.
    assert (
        'params.set("scope_type"'
        not in text
    )


def test_access_control_local_editor_is_removed() -> None:
    text = _read(
        "modules/access-control/"
        "AccessControl.jsx"
    )

    forbidden = (
        "updateAccessConfig",
        "DEFAULT_ACCESS_CONFIG",
        "ACCESS_MODULES",
        "MODULE_DETAIL_CONFIG",
        "SCOPE_OPTIONS",
    )

    for needle in forbidden:
        assert needle not in text

    assert (
        "Veritaban? Yetki Otoritesi"
        in text
    )


def test_spoofable_identity_headers_are_never_created() -> None:
    for path in _frontend_sources():
        text = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        relative = path.relative_to(
            REPO_ROOT
        ).as_posix()

        for header in (
            "X-User-Email",
            "X-OPEX-User",
            "X-OPEX-Role",
        ):
            if header not in text:
                continue

            # Only the central API client's
            # explicit deletion is permitted.
            assert relative == (
                "src/api/client.js"
            )

            assert (
                f'headers.delete("{header}")'
                in text
            )


def test_budget_intelligence_uses_authenticated_api_client() -> None:
    text = _read(
        "modules/budget-intelligence/"
        "BudgetIntelligence.jsx"
    )

    assert (
        'from"../../api/client.js"'
        in text
    )
    assert "apiGet" in text

    forbidden = (
        "localhost:8000",
        "127.0.0.1:8000",
        ":8000",
        "VITE_API_BASE",
        "fetch(",
        "const fallback={",
        "catch{return fb}",
        "opex_access_token",
        "opex_session_token",
    )

    for needle in forbidden:
        assert needle not in text, (
            f"Budget frontend security bypass "
            f"reintroduced: {needle}"
        )

    assert "EMPTY_DATA" in text
    assert "setApiError" in text


def test_dockos_has_no_synthetic_admin_authority() -> None:
    permissions = _read(
        "modules/DockOS/dockosPermissions.js"
    )
    dashboard = _read(
        "modules/DockOS/DockOSDashboardBase.jsx"
    )
    banner = _read(
        "modules/DockOS/DockOSPermissionBanner.jsx"
    )

    for text in (
        permissions,
        dashboard,
        banner,
    ):
        assert "isAdmin" not in text

    assert (
        'canDockOSAction("approve") ||'
        not in permissions
    )


def test_dockos_uncatalogued_privileged_screens_are_quarantined() -> None:
    dashboard = _read(
        "modules/DockOS/DockOSDashboardBase.jsx"
    )

    components = (
        "PlanningPoUpload",
        "CapacityManagement",
        "AuditLog",
        "NotificationCenter",
        "SupplierAccessManagement",
    )

    for component in components:
        assert component not in dashboard

    privileged_tabs = (
        '"planning"',
        '"capacity"',
        '"audit"',
        '"notifications"',
        '"access"',
    )

    for key in privileged_tabs:
        assert key not in dashboard


def test_dockos_remaining_tabs_use_exact_db_permissions() -> None:
    dashboard = _read(
        "modules/DockOS/DockOSDashboardBase.jsx"
    )

    required = (
        'canDockOSFeature("supplierAppointments")',
        'canDockOSAction("create")',
        'canDockOSFeature("vehicleTracking")',
        'canDockOSAction("edit")',
        'canDockOSFeature("dashboard")',
    )

    for value in required:
        assert value in dashboard

    assert "getDockOSPermissionSnapshot" not in dashboard
    assert "Port 8000" not in dashboard
    assert "Gateway API" in dashboard


def test_planogram_legacy_iframe_is_phase1_quarantined() -> None:
    studio = _read(
        "modules/planogram/PlanogramStudio.jsx"
    )

    forbidden = (
        "VITE_PLANAI_LEGACY_URL",
        "localhost:5174",
        "PLANAI_URL",
        "<iframe",
        "postMessage",
        "OPEX_PLANOGRAM_SESSION",
        "PLANOGRAM_READY",
        "PLANOGRAM_SESSION_ACCEPTED",
        "getAccessToken",
        "accessToken",
        "Authorization",
        "Bearer",
    )

    for value in forbidden:
        assert value not in studio

    assert (
        "Phase 1 Security Quarantine"
        in studio
    )


def test_frontend_never_posts_provider_bearer_to_child_window() -> None:
    for path in _frontend_sources():
        text = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        lowered = text.lower()

        if "postmessage" not in lowered:
            continue

        assert (
            "accesstoken" not in lowered
        ), (
            "Access token exposed through "
            f"postMessage in {path.relative_to(REPO_ROOT)}"
        )

        assert (
            "bearer" not in lowered
        ), (
            "Bearer credential exposed through "
            f"postMessage in {path.relative_to(REPO_ROOT)}"
        )


def test_planogram_has_no_legacy_cross_origin_auth_bridge() -> None:
    module_root = (
        FRONTEND_ROOT /
        "modules/planogram"
    )

    for path in module_root.rglob("*"):
        if (
            not path.is_file()
            or path.suffix
            not in {".js", ".jsx", ".ts", ".tsx"}
        ):
            continue

        text = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        forbidden = (
            "plonagram_access_token",
            "VITE_PLANAI_LEGACY_URL",
            "localhost:5174",
            "OPEX_PLANOGRAM_SESSION",
        )

        for value in forbidden:
            assert value not in text
