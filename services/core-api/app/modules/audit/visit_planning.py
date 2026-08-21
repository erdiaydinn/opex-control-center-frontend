from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .schemas import StrictModel

AuditVisitType = Literal[
    "FULL_AUDIT",
    "QUICK_AUDIT",
    "FOCUS_AUDIT",
    "CUSTOM_AUDIT",
    "PEOPLE_VISIT",
    "SPECIAL_VISIT",
]
AuditVisitScoreMode = Literal["OFFICIAL_COMPLIANCE", "FOCUS_SCORE", "NO_SCORE"]
AuditVisitScopeState = Literal["IN_SCOPE", "OUT_OF_SCOPE"]
AuditVisitNoteType = Literal[
    "HUMAN_CONVERSATION",
    "OPERATION_OBSERVATION",
    "POSITIVE_PRACTICE",
    "FOLLOW_UP",
    "OTHER",
]
AuditSourceMode = Literal["checklist", "photo", "video", "guided_video", "mixed"]


class AuditVisitScopeEntry(StrictModel):
    section_key: str = Field(min_length=1, max_length=180)
    item_key: str = Field(min_length=1, max_length=180)
    state: AuditVisitScopeState
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_scope_reason(self) -> AuditVisitScopeEntry:
        if self.state == "OUT_OF_SCOPE" and not (self.reason or "").strip():
            raise ValueError("OUT_OF_SCOPE requires an explicit visit-scope reason")
        return self


class AuditVisitCreate(StrictModel):
    visit_type: AuditVisitType
    title: str = Field(min_length=1, max_length=300)
    location_id: str = Field(min_length=1, max_length=120)
    program_key: str | None = Field(default=None, min_length=1, max_length=120)
    program_version: int | None = Field(default=None, gt=0)
    scope: tuple[AuditVisitScopeEntry, ...] = Field(default=(), max_length=1000)
    people_topics: tuple[str, ...] = Field(default=(), max_length=50)
    rationale: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_visit_contract(self) -> AuditVisitCreate:
        has_program = self.program_key is not None and self.program_version is not None
        partial_program = (self.program_key is None) != (self.program_version is None)
        if partial_program:
            raise ValueError("program_key and program_version must be supplied together")

        identities = tuple((entry.section_key, entry.item_key) for entry in self.scope)
        if len(set(identities)) != len(identities):
            raise ValueError("visit scope item identities must be unique")

        if self.visit_type == "PEOPLE_VISIT":
            if has_program:
                raise ValueError("PEOPLE_VISIT cannot claim an audit program")
            if self.scope:
                raise ValueError("PEOPLE_VISIT cannot carry scored audit scope")
            if not self.people_topics:
                raise ValueError("PEOPLE_VISIT requires at least one visit topic")
            return self

        if not has_program:
            raise ValueError("scored visits require an approved audit program version")
        if not self.scope:
            raise ValueError("scored visits require an explicit question scope manifest")
        if not any(entry.state == "IN_SCOPE" for entry in self.scope):
            raise ValueError("scored visits require at least one IN_SCOPE question")

        if self.visit_type == "FULL_AUDIT" and any(
            entry.state != "IN_SCOPE" for entry in self.scope
        ):
            raise ValueError(
                "FULL_AUDIT cannot hide approved questions as OUT_OF_SCOPE; use runtime N/A proof"
            )
        return self


class AuditVisitPlan(StrictModel):
    visit_type: AuditVisitType
    score_mode: AuditVisitScoreMode
    official_compliance_eligible: bool
    scope_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    in_scope_count: int = Field(ge=0)
    out_of_scope_count: int = Field(ge=0)
    section_count: int = Field(ge=0)
    people_topic_count: int = Field(ge=0)


class AuditVisitRunStart(StrictModel):
    source_mode: AuditSourceMode = "checklist"
    field_mission_id: UUID | None = None


class AuditVisitNoteCreate(StrictModel):
    note_type: AuditVisitNoteType
    note: str = Field(min_length=1, max_length=8000)
    source_refs: tuple[str, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def validate_note_refs(self) -> AuditVisitNoteCreate:
        if any(not ref.strip() or len(ref) > 500 for ref in self.source_refs):
            raise ValueError("visit note source refs must be non-blank and <= 500 characters")
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("visit note source refs must be unique")
        return self


def _scope_fingerprint(payload: AuditVisitCreate) -> str:
    canonical = json.dumps(
        {
            "visit_type": payload.visit_type,
            "location_id": payload.location_id,
            "program_key": payload.program_key,
            "program_version": payload.program_version,
            "scope": [entry.model_dump(mode="json") for entry in payload.scope],
            "people_topics": list(payload.people_topics),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_visit_plan(payload: AuditVisitCreate) -> AuditVisitPlan:
    if payload.visit_type == "FULL_AUDIT":
        score_mode: AuditVisitScoreMode = "OFFICIAL_COMPLIANCE"
        official = True
    elif payload.visit_type == "PEOPLE_VISIT":
        score_mode = "NO_SCORE"
        official = False
    else:
        score_mode = "FOCUS_SCORE"
        official = False

    return AuditVisitPlan(
        visit_type=payload.visit_type,
        score_mode=score_mode,
        official_compliance_eligible=official,
        scope_fingerprint=_scope_fingerprint(payload),
        in_scope_count=sum(entry.state == "IN_SCOPE" for entry in payload.scope),
        out_of_scope_count=sum(entry.state == "OUT_OF_SCOPE" for entry in payload.scope),
        section_count=len({entry.section_key for entry in payload.scope}),
        people_topic_count=len(payload.people_topics),
    )
