from datetime import datetime, timezone

import pytest

from app.platform.business_glossary.jarvis import JarvisGlossaryAnswerUnavailable, answer_business_term
from app.platform.business_glossary.models import (
    GlossaryAliasBinding,
    GlossaryAliasKind,
    GlossaryConceptRelation,
    GlossaryRelationKind,
    GlossaryScope,
    GlossaryStatus,
    GlossaryTerm,
    LocalizedText,
)
from app.platform.business_glossary.resolver import GlossaryResolutionError, resolve_term

AT = datetime(2026, 8, 17, 12, 15, tzinfo=timezone.utc)


def _term(
    *,
    tenant: str,
    concept: str,
    key: str,
    definition: str,
    domain: str | None = None,
    business_unit: str | None = None,
    aliases: list[GlossaryAliasBinding] | None = None,
    relations: list[GlossaryConceptRelation] | None = None,
) -> GlossaryTerm:
    return GlossaryTerm(
        concept_id=concept,
        canonical_key=key,
        scope=GlossaryScope(tenant_id=tenant, business_unit=business_unit, domain=domain),
        status=GlossaryStatus.EFFECTIVE,
        version=1,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        display_name=LocalizedText(values={"tr": key, "en": key}),
        short_definition=LocalizedText(values={"tr": definition, "en": definition}),
        alias_bindings=aliases or [],
        concept_relations=relations or [],
        owner="semantic-governance",
    )


def test_synonym_and_acronym_resolve_to_same_canonical_concept_with_graph_context() -> None:
    receiving = _term(
        tenant="tenant-a",
        concept="goods-receiving",
        key="goods_receiving",
        definition="Inbound goods receiving",
        domain="inbound",
        aliases=[
            GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="mal kabul"),
            GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="receiving"),
            GlossaryAliasBinding(kind=GlossaryAliasKind.ACRONYM, value="GR"),
        ],
        relations=[
            GlossaryConceptRelation(kind=GlossaryRelationKind.PARENT, target_concept_id="inbound-operations"),
            GlossaryConceptRelation(kind=GlossaryRelationKind.RELATED, target_concept_id="putaway"),
        ],
    )

    for query in ("mal kabul", "receiving", "GR"):
        answer = resolve_term(
            [receiving],
            tenant_id="tenant-a",
            query=query,
            locale="tr",
            domain="inbound",
            at=AT,
        )
        assert answer.concept_id == "goods-receiving"
        assert answer.canonical_key == "goods_receiving"
        assert {binding.kind for binding in answer.alias_bindings} == {
            GlossaryAliasKind.SYNONYM,
            GlossaryAliasKind.ACRONYM,
        }
        assert {(edge.kind, edge.target_concept_id) for edge in answer.concept_relations} == {
            (GlossaryRelationKind.PARENT, "inbound-operations"),
            (GlossaryRelationKind.RELATED, "putaway"),
        }


def test_missing_scope_fails_closed_with_same_tenant_candidate_context() -> None:
    inbound = _term(
        tenant="tenant-a",
        concept="goods-receiving",
        key="goods_receiving",
        definition="Inbound receiving",
        domain="inbound",
        aliases=[GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="receiving")],
    )
    market = _term(
        tenant="tenant-a",
        concept="commercial-receiving",
        key="commercial_receiving",
        definition="Commercial receiving",
        business_unit="Market",
        aliases=[GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="receiving")],
    )
    other_tenant = _term(
        tenant="tenant-b",
        concept="tenant-b-receiving",
        key="receiving",
        definition="Must never leak",
        domain="finance",
        aliases=[GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="receiving")],
    )

    with pytest.raises(GlossaryResolutionError, match="scope context is required") as exc_info:
        resolve_term(
            [inbound, market, other_tenant],
            tenant_id="tenant-a",
            query="receiving",
            locale="en",
            at=AT,
        )

    candidates = exc_info.value.candidates
    assert {candidate.concept_id for candidate in candidates} == {
        "goods-receiving",
        "commercial-receiving",
    }
    assert {candidate.scope.tenant_id for candidate in candidates} == {"tenant-a"}
    assert {candidate.scope.domain for candidate in candidates} == {"inbound", None}
    assert {candidate.scope.business_unit for candidate in candidates} == {None, "Market"}


def test_jarvis_preserves_safe_ambiguity_context_instead_of_guessing() -> None:
    terms = [
        _term(
            tenant="tenant-a",
            concept="goods-receiving",
            key="goods_receiving",
            definition="Inbound receiving",
            domain="inbound",
            aliases=[GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="receiving")],
        ),
        _term(
            tenant="tenant-a",
            concept="commercial-receiving",
            key="commercial_receiving",
            definition="Commercial receiving",
            business_unit="Market",
            aliases=[GlossaryAliasBinding(kind=GlossaryAliasKind.SYNONYM, value="receiving")],
        ),
    ]

    with pytest.raises(JarvisGlossaryAnswerUnavailable, match="scope context is required") as exc_info:
        answer_business_term(
            terms,
            tenant_id="tenant-a",
            query="receiving",
            locale="tr",
            at=AT,
        )
    assert len(exc_info.value.candidates) == 2
    assert {candidate.scope.tenant_id for candidate in exc_info.value.candidates} == {"tenant-a"}
