from pathlib import Path

from app.acceptance.matrix import (
    REQUIRED_CROSS,
    REQUIRED_LANGS,
    REQUIRED_MODULES,
    REQUIRED_PEN,
    load_acceptance_matrix,
)

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs/governance/eay_real_acceptance_matrix.json"


def test_real_acceptance_matrix_covers_standalone_cross_security_and_languages() -> None:
    matrix = load_acceptance_matrix(MATRIX)
    assert REQUIRED_MODULES <= set(matrix["module_uat"])
    assert REQUIRED_CROSS <= set(matrix["cross_module_uat"])
    assert REQUIRED_PEN <= set(matrix["security_penetration"])
    assert REQUIRED_LANGS <= set(matrix["accessibility_language"])
    assert {
        "keyboard_only",
        "screen_reader",
        "large_text",
        "reduced_motion",
        "mobile_ergonomics",
    } <= set(matrix["accessibility_language"])
    assert {
        "login_navigation",
        "workforce_checkin",
        "inventory_scan",
        "field_capture",
        "planogram_review",
        "dock_booking",
        "budget_approval",
        "academy_learning",
        "jarvis_question",
    } <= set(matrix["common_flows"])
