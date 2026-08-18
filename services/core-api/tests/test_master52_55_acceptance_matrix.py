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
    assert set(matrix["module_uat"]) >= REQUIRED_MODULES
    assert set(matrix["cross_module_uat"]) >= REQUIRED_CROSS
    assert set(matrix["security_penetration"]) >= REQUIRED_PEN
    assert set(matrix["accessibility_language"]) >= REQUIRED_LANGS
    assert set(matrix["accessibility_language"]) >= {
        "keyboard_only",
        "screen_reader",
        "large_text",
        "reduced_motion",
        "mobile_ergonomics",
    }
    assert set(matrix["common_flows"]) >= {
        "login_navigation",
        "workforce_checkin",
        "inventory_scan",
        "field_capture",
        "planogram_review",
        "dock_booking",
        "budget_approval",
        "academy_learning",
        "jarvis_question",
    }
