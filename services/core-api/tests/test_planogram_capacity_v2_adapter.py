from types import SimpleNamespace

from app.modules.planogram import engine_adapter


def _validator(report):
    return SimpleNamespace(validate_planogram_capacity_v2=lambda plan: report)


def test_capacity_v2_veto_blocks_publishable(monkeypatch):
    monkeypatch.setattr(
        engine_adapter,
        "_load_capacity_validator",
        lambda: _validator(
            {
                "contract": "capacity-v2",
                "available": True,
                "valid": False,
                "violation_count": 1,
                "warning_count": 0,
                "violations": [{"code": "shelf_full_depth_weight_exceeded"}],
            }
        ),
    )
    result = engine_adapter._apply_capacity_v2_veto(
        {
            "publishable": True,
            "production_ready": True,
            "solver_optimizer_allowed": True,
            "planogram": {"aisles": []},
            "physical_truth": {"blockers": []},
            "summary": {},
        }
    )
    assert result["publishable"] is False
    assert result["production_ready"] is False
    assert result["solver_optimizer_allowed"] is False
    assert (
        "physical_capacity_v2:shelf_full_depth_weight_exceeded"
        in result["physical_truth"]["blockers"]
    )


def test_capacity_v2_valid_preserves_existing_publishability(monkeypatch):
    monkeypatch.setattr(
        engine_adapter,
        "_load_capacity_validator",
        lambda: _validator(
            {
                "contract": "capacity-v2",
                "available": True,
                "valid": True,
                "violation_count": 0,
                "warning_count": 1,
                "violations": [],
            }
        ),
    )
    result = engine_adapter._apply_capacity_v2_veto(
        {
            "publishable": True,
            "production_ready": True,
            "planogram": {"aisles": []},
            "summary": {},
        }
    )
    assert result["publishable"] is True
    assert result["physical_capacity_v2"]["valid"] is True
