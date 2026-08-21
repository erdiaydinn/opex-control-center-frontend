from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillRequirement:
    skill_key: str
    required_level: int


@dataclass(frozen=True)
class SkillProficiency:
    skill_key: str
    observed_level: int
    evidence_ref: str


@dataclass(frozen=True)
class LearningPathOutcome:
    path_key: str
    skill_key: str
    target_level: int


@dataclass(frozen=True)
class SkillGap:
    skill_key: str
    required_level: int
    current_level: int
    gap: int


def compute_skill_gaps(
    requirements: Iterable[SkillRequirement],
    proficiencies: Iterable[SkillProficiency],
) -> tuple[SkillGap, ...]:
    current = {
        item.skill_key: max(0, min(5, item.observed_level)) for item in proficiencies
    }
    gaps: list[SkillGap] = []
    for requirement in sorted(requirements, key=lambda item: item.skill_key):
        level = current.get(requirement.skill_key, 0)
        if level < requirement.required_level:
            gaps.append(
                SkillGap(
                    skill_key=requirement.skill_key,
                    required_level=requirement.required_level,
                    current_level=level,
                    gap=requirement.required_level - level,
                )
            )
    return tuple(gaps)


def recommend_learning_paths(
    gaps: Iterable[SkillGap],
    outcomes: Iterable[LearningPathOutcome],
) -> tuple[str, ...]:
    missing = {gap.skill_key: gap.required_level for gap in gaps}
    coverage: dict[str, set[str]] = {}
    for outcome in outcomes:
        required = missing.get(outcome.skill_key)
        if required is not None and outcome.target_level >= required:
            coverage.setdefault(outcome.path_key, set()).add(outcome.skill_key)

    remaining = set(missing)
    selected: list[str] = []
    while remaining:
        candidates = [
            (path, len(skills & remaining))
            for path, skills in coverage.items()
            if skills & remaining
        ]
        if not candidates:
            break
        best_path = min(candidates, key=lambda item: (-item[1], item[0]))[0]
        selected.append(best_path)
        remaining -= coverage[best_path]
    return tuple(selected)
