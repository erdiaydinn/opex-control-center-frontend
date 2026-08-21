from decimal import Decimal

from app.modules.workforce.skill_capacity import SkillDemand, WorkerSkillCapacity, allocate_skill_capacity


def worker(employee_id: str, hours: str, *skills: str):
    return WorkerSkillCapacity(
        employee_id=employee_id,
        available_hours=Decimal(hours),
        skills=frozenset(skills),
    )


def test_multi_skilled_worker_hours_are_not_double_counted():
    result = allocate_skill_capacity(
        SkillDemand(required_hours={"picking": Decimal("6"), "inbound": Decimal("4")}),
        (
            worker("specialist", "4", "inbound"),
            worker("multi", "6", "picking", "inbound"),
        ),
    )
    assert result.deficit_hours["inbound"] == Decimal("0")
    assert result.deficit_hours["picking"] == Decimal("0")
    assert sum(result.allocated_hours.values()) == Decimal("10")


def test_skill_specific_shortage_is_visible_even_when_total_headcount_hours_look_sufficient():
    result = allocate_skill_capacity(
        SkillDemand(required_hours={"picking": Decimal("8"), "inbound": Decimal("4")}),
        (
            worker("picker-1", "8", "picking"),
            worker("picker-2", "4", "picking"),
        ),
    )
    assert result.total_deficit_hours == Decimal("4")
    assert result.deficit_hours["inbound"] == Decimal("4")


def test_specialist_capacity_is_used_before_multi_skill_capacity_for_scarce_skill():
    result = allocate_skill_capacity(
        SkillDemand(required_hours={"inbound": Decimal("4"), "picking": Decimal("8")}),
        (
            worker("inbound-specialist", "4", "inbound"),
            worker("multi", "8", "inbound", "picking"),
        ),
    )
    assert result.total_deficit_hours == Decimal("0")
    assert result.unused_worker_hours["inbound-specialist"] == Decimal("0")
    assert result.unused_worker_hours["multi"] == Decimal("0")
