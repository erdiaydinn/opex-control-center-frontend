from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SkillDemand:
    required_hours: dict[str, Decimal]

    def __post_init__(self) -> None:
        if not self.required_hours or any(not skill or hours < ZERO for skill, hours in self.required_hours.items()):
            raise ValueError("skill demand requires non-negative hours and named skills")


@dataclass(frozen=True, slots=True)
class WorkerSkillCapacity:
    employee_id: str
    available_hours: Decimal
    skills: frozenset[str]

    def __post_init__(self) -> None:
        if not self.employee_id or self.available_hours < ZERO or not self.skills:
            raise ValueError("worker skill capacity is invalid")


@dataclass(frozen=True, slots=True)
class SkillCapacityResult:
    allocated_hours: dict[str, Decimal]
    deficit_hours: dict[str, Decimal]
    unused_worker_hours: dict[str, Decimal]

    @property
    def total_deficit_hours(self) -> Decimal:
        return sum(self.deficit_hours.values(), ZERO)


def allocate_skill_capacity(demand: SkillDemand, workers: tuple[WorkerSkillCapacity, ...]) -> SkillCapacityResult:
    """Allocate each worker hour once, prioritizing the scarcest demanded skills.

    This is an auditable feasibility allocator, not the final shift optimizer. The
    resulting deficits can be consumed by optimization/replanning without assuming
    that every scheduled employee is interchangeable.
    """
    remaining = {worker.employee_id: worker.available_hours for worker in workers}
    if len(remaining) != len(workers):
        raise ValueError("employee_id must be unique in skill capacity input")

    worker_by_id = {worker.employee_id: worker for worker in workers}

    def candidate_capacity(skill: str) -> Decimal:
        return sum((worker.available_hours for worker in workers if skill in worker.skills), ZERO)

    skill_order = sorted(demand.required_hours, key=lambda skill: (candidate_capacity(skill), skill))
    allocated: dict[str, Decimal] = {}
    deficits: dict[str, Decimal] = {}

    for skill in skill_order:
        needed = demand.required_hours[skill]
        allocation = ZERO
        candidates = [worker for worker in workers if skill in worker.skills and remaining[worker.employee_id] > ZERO]
        candidates.sort(key=lambda worker: (len(worker.skills), worker.employee_id))
        for worker in candidates:
            if needed <= ZERO:
                break
            employee_id = worker.employee_id
            amount = min(needed, remaining[employee_id])
            remaining[employee_id] -= amount
            needed -= amount
            allocation += amount
        allocated[skill] = allocation
        deficits[skill] = max(ZERO, needed)

    return SkillCapacityResult(
        allocated_hours=allocated,
        deficit_hours=deficits,
        unused_worker_hours=remaining,
    )
