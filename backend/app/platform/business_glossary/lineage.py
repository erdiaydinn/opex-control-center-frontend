from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .models import GlossaryAnswer


class GlossaryLineageError(ValueError):
    pass


class GlossaryLineageAssetKind(StrEnum):
    DATASET = "dataset"
    API_FIELD = "api_field"
    DASHBOARD = "dashboard"


class GlossaryLineageRelation(StrEnum):
    SOURCE = "source"
    EXPOSED_AS = "exposed_as"
    USED_BY = "used_by"


_ALLOWED_RELATIONS = {
    GlossaryLineageAssetKind.DATASET: {GlossaryLineageRelation.SOURCE},
    GlossaryLineageAssetKind.API_FIELD: {GlossaryLineageRelation.EXPOSED_AS},
    GlossaryLineageAssetKind.DASHBOARD: {GlossaryLineageRelation.USED_BY},
}


class GlossaryLineageBinding(BaseModel):
    tenant_id: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    glossary_version: int = Field(ge=1)
    asset_kind: GlossaryLineageAssetKind
    relation: GlossaryLineageRelation
    asset_ref: str = Field(min_length=1)
    display_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_binding(self) -> "GlossaryLineageBinding":
        if not self.asset_ref.strip():
            raise ValueError("lineage asset_ref must not be blank")
        if self.relation not in _ALLOWED_RELATIONS[self.asset_kind]:
            raise ValueError(f"invalid lineage relation {self.relation.value} for {self.asset_kind.value}")
        if self.display_label is not None and not self.display_label.strip():
            raise ValueError("lineage display_label must not be blank")
        return self


class GlossaryLineageView(BaseModel):
    tenant_id: str
    concept_id: str
    glossary_version: int
    source_datasets: list[GlossaryLineageBinding] = Field(default_factory=list)
    api_fields: list[GlossaryLineageBinding] = Field(default_factory=list)
    dashboards: list[GlossaryLineageBinding] = Field(default_factory=list)
    authoritative: bool = True


def lineage_for_answer(
    answer: GlossaryAnswer,
    bindings: list[GlossaryLineageBinding],
) -> GlossaryLineageView:
    """Return page-ready lineage only for the exact authoritative glossary version."""
    if not answer.authoritative:
        raise GlossaryLineageError("lineage requires an authoritative glossary answer")

    tenant_id = answer.scope.tenant_id
    exact = [
        binding
        for binding in bindings
        if binding.tenant_id == tenant_id
        and binding.concept_id == answer.concept_id
        and binding.glossary_version == answer.version
    ]
    exact.sort(key=lambda item: (item.asset_kind.value, item.relation.value, item.asset_ref))

    return GlossaryLineageView(
        tenant_id=tenant_id,
        concept_id=answer.concept_id,
        glossary_version=answer.version,
        source_datasets=[item for item in exact if item.asset_kind is GlossaryLineageAssetKind.DATASET],
        api_fields=[item for item in exact if item.asset_kind is GlossaryLineageAssetKind.API_FIELD],
        dashboards=[item for item in exact if item.asset_kind is GlossaryLineageAssetKind.DASHBOARD],
    )
