import re
from pathlib import Path

from app.core.permission_catalog import (
    ACTIONS,
    ALL_PERMISSION_KEYS,
    FEATURES,
    ROUTE_MODULES,
    SYSTEM_ROLE_PERMISSIONS,
    action_permission,
    feature_permission,
    module_permission,
)

FRONTEND_ROOT = Path(__file__).resolve().parents[3] / "src"


def _read(relative: str) -> str:
    return (FRONTEND_ROOT / relative).read_text(
        encoding="utf-8-sig",
        errors="ignore",
    )


def _array_strings(text: str, name: str) -> set[str]:
    match = re.search(
        rf"const\s+{re.escape(name)}\s*=\s*\[(.*?)\];",
        text,
        re.S,
    )
    assert match is not None, f"{name} not found"
    return set(re.findall(r'["\']([^"\']+)["\']', match.group(1)))


def _object_values(text: str, name: str) -> set[str]:
    match = re.search(
        rf"(?:export\s+)?const\s+{re.escape(name)}\s*=\s*\{{(.*?)\}};",
        text,
        re.S,
    )
    assert match is not None, f"{name} not found"
    return set(
        re.findall(
            r':\s*["\']([^"\']+)["\']',
            match.group(1),
        )
    )


def test_permission_keys_are_unique_and_canonical() -> None:
    assert ALL_PERMISSION_KEYS
    assert len(ALL_PERMISSION_KEYS) == len(set(ALL_PERMISSION_KEYS))

    for key in ALL_PERMISSION_KEYS:
        assert re.fullmatch(
            r"(?:module|feature|action):"
            r"[a-z_][a-z0-9_]*:"
            r"[A-Za-z][A-Za-z0-9_]*",
            key,
        ), key


def test_frontend_route_modules_are_catalogued() -> None:
    app = _read("App.jsx")

    route_modules = set(
        re.findall(
            r'moduleKey\s*=\s*["\']([^"\']+)["\']',
            app,
        )
    )

    assert route_modules == ROUTE_MODULES

    for module in route_modules:
        assert module_permission(module) in ALL_PERMISSION_KEYS

    admin_pairs = re.findall(
        r'moduleKey\s*=\s*["\']([^"\']+)["\']'
        r'[^>]*action\s*=\s*["\']([^"\']+)["\']',
        app,
        re.S,
    )

    for module, action in admin_pairs:
        assert module_permission(module, action) in ALL_PERMISSION_KEYS


def test_planogram_contract_is_catalogued() -> None:
    text = _read("modules/planogram/PlanogramStudio.jsx")

    features = _array_strings(text, "PLANOGRAM_FEATURES")
    actions = _array_strings(text, "PLANOGRAM_ACTIONS")

    assert features == FEATURES["planogram"]
    assert actions == ACTIONS["planogram"]

    for feature in features:
        assert feature_permission("planogram", feature) in ALL_PERMISSION_KEYS

    for action in actions:
        assert action_permission("planogram", action) in ALL_PERMISSION_KEYS


def test_dockos_contract_is_catalogued() -> None:
    text = _read("modules/DockOS/dockosPermissions.js")

    features = _object_values(text, "DOCKOS_FEATURES")
    actions = _object_values(text, "DOCKOS_ACTIONS")

    assert features == FEATURES["dockos"]
    assert actions == ACTIONS["dockos"]

    for feature in features:
        assert feature_permission("dockos", feature) in ALL_PERMISSION_KEYS

    for action in actions:
        assert action_permission("dockos", action) in ALL_PERMISSION_KEYS


def test_workforce_contract_is_catalogued() -> None:
    text = _read("modules/workforce/WorkforceControl.jsx")

    features = set(
        re.findall(
            r'feature\s*:\s*["\']([^"\']+)["\']',
            text,
        )
    )

    actions = set(
        re.findall(
            r'allowed\(\s*["\']([^"\']+)["\']\s*\)',
            text,
        )
    )

    assert features == FEATURES["workforce"]
    assert actions == ACTIONS["workforce"]

    for feature in features:
        assert feature_permission("workforce", feature) in ALL_PERMISSION_KEYS

    for action in actions:
        assert action_permission("workforce", action) in ALL_PERMISSION_KEYS


def test_recruitment_actions_are_catalogued() -> None:
    text = _read("modules/recruitment/RecruitmentControl.jsx")

    ui_actions = set(
        re.findall(
            r'canAction\(\s*["\']recruitment["\']\s*,'
            r'\s*["\']([^"\']+)["\']\s*\)',
            text,
        )
    )
    canonical = ACTIONS["recruitment"]

    # Recruitment has server-only authorities as well as UI capability checks.
    # Every UI check must be canonical, while the canonical set must preserve the
    # complete governed vacancy/evidence/settings/notification lifecycle.
    assert ui_actions
    assert ui_actions <= canonical
    assert canonical == frozenset(
        {
            "viewRecruitment",
            "createRecruitmentRequest",
            "approveRecruitmentRequest",
            "viewRecruitmentEvidence",
            "manageRecruitmentNorms",
            "manageRecruitmentActuals",
            "manageRecruitmentSettings",
            "manageRecruitmentNotifications",
        }
    )

    for action in canonical:
        assert action_permission("recruitment", action) in ALL_PERMISSION_KEYS


def test_system_roles_start_fail_closed() -> None:
    assert SYSTEM_ROLE_PERMISSIONS["super_admin"] == ALL_PERMISSION_KEYS

    assert SYSTEM_ROLE_PERMISSIONS["operator"] == frozenset()
    assert SYSTEM_ROLE_PERMISSIONS["viewer"] == frozenset()

    assert SYSTEM_ROLE_PERMISSIONS["platform_admin"] == frozenset(
        {
            module_permission("admin_access", "view"),
        }
    )
