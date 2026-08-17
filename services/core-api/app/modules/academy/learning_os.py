from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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


def compute_skill_gaps(requirements: Iterable[SkillRequirement], proficiencies: Iterable[SkillProficiency]) -> tuple[SkillGap, ...]:
    current={item.skill_key:max(0,min(5,item.observed_level)) for item in proficiencies}
    gaps=[]
    for req in sorted(requirements,key=lambda item:item.skill_key):
        level=current.get(req.skill_key,0)
        if level < req.required_level:
            gaps.append(SkillGap(req.skill_key,req.required_level,level,req.required_level-level))
    return tuple(gaps)


def recommend_learning_paths(gaps: Iterable[SkillGap], outcomes: Iterable[LearningPathOutcome]) -> tuple[str, ...]:
    missing={gap.skill_key:gap.required_level for gap in gaps}
    coverage: dict[str,set[str]]={}
    for outcome in outcomes:
        required=missing.get(outcome.skill_key)
        if required is not None and outcome.target_level>=required:
            coverage.setdefault(outcome.path_key,set()).add(outcome.skill_key)
    remaining=set(missing)
    selected=[]
    while remaining:
        candidates=[(path,len(skills & remaining)) for path,skills in coverage.items() if skills & remaining]
        if not candidates:
            break
        best=min(candidates,key=lambda item:(-item[1],item[0]))[0]
        selected.append(best)
        remaining-=coverage[best]
    return tuple(selected)
