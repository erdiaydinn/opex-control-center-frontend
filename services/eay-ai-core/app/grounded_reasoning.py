"""Deterministic decision-quality guard for grounded Jarvis answers.

This module does not ask a model to expose private reasoning. It evaluates the
observable answer contract against retrieved evidence, query risk and citation
coverage, then applies fail-closed confidence/human-review calibration.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

DECISION_QUALITY_CONTRACT = "grounded-decision-quality-v1"

LEGAL_TERMS = {
    "law",
    "legal",
    "legislation",
    "regulation",
    "regulatory",
    "mevzuat",
    "kanun",
    "yasa",
    "yasal",
    "hukuk",
    "hukuki",
    "yonetmelik",
    "yönetmelik",
    "resmi gazete",
    "resmî gazete",
    "zorunlu",
    "ceza",
}
COMPANY_TERMS = {
    "company policy",
    "internal policy",
    "sop",
    "prosedur",
    "prosedür",
    "politika",
    "sirket kurali",
    "şirket kuralı",
    "standardimiz",
    "standardımız",
}
STANDARD_TERMS = {
    "industry standard",
    "best practice",
    "standard",
    "standart",
    "iyi uygulama",
}
OPERATIONAL_TERMS = {
    "kpi",
    "nsfr",
    "pfr",
    "refund",
    "picking",
    "putaway",
    "prep",
    "otp",
    "order",
    "siparis",
    "sipariş",
    "depo",
    "store",
    "warehouse",
    "vardiya",
    "shift",
    "inventory",
    "stok",
    "planogram",
    "planogram",
    "operasyon",
    "operational",
}

HUMAN_REVIEW_TERMS = {
    "fire",
    "terminate",
    "dismiss",
    "disciplinary",
    "employee exit",
    "isten cikar",
    "işten çıkar",
    "fesih",
    "disiplin",
    "hire",
    "recruit",
    "maas",
    "maaş",
    "salary",
    "payment",
    "odeme",
    "ödeme",
    "budget approval",
    "approve budget",
    "invoice",
    "fatura",
    "refund customer",
    "musteriye iade",
    "müşteriye iade",
    "send email",
    "mail gonder",
    "mail gönder",
    "publish",
    "external communication",
    "legal notice",
    "ceza",
    "penalty",
}

_SECTION_BY_LAYER = {
    "legal": "legal",
    "company": "company",
    "standard": "standards",
    "operational": "operational",
}


def _normalize(text: Any) -> str:
    value = "" if text is None else str(text)
    value = value.casefold().replace("ı", "i")
    return re.sub(r"\s+", " ", value).strip()


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(_normalize(term) in text for term in terms)


def infer_required_layers(message: str) -> list[str]:
    """Infer evidence layers explicitly implicated by the user's wording.

    `request.layers` is an allowlist, not proof that every layer is semantically
    required. The guard therefore only makes a layer mandatory when the question
    itself signals that authority domain.
    """
    text = _normalize(message)
    layers: list[str] = []
    if _contains_any(text, LEGAL_TERMS):
        layers.append("legal")
    if _contains_any(text, COMPANY_TERMS):
        layers.append("company")
    if _contains_any(text, STANDARD_TERMS):
        layers.append("standard")
    if _contains_any(text, OPERATIONAL_TERMS):
        layers.append("operational")
    return layers


class DecisionQualityReport(BaseModel):
    contract: str = DECISION_QUALITY_CONTRACT
    required_layers: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    binding_legal_count: int = 0
    cited_evidence_count: int = 0
    evidence_coverage_pct: float = 0.0
    evidence_sufficient: bool = False
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    confidence_cap: float = 0.0
    human_review_required: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _section_citations(answer: Any, layer: str) -> list[str]:
    section_name = _SECTION_BY_LAYER[layer]
    section = getattr(answer, section_name, None)
    citations = getattr(section, "citations", None) if section is not None else None
    return [str(item) for item in (citations or []) if str(item).strip()]


def _section_status(answer: Any, layer: str) -> str:
    section_name = _SECTION_BY_LAYER[layer]
    section = getattr(answer, section_name, None)
    return _normalize(getattr(section, "status", ""))


def _is_claiming_status(status: str) -> bool:
    return status not in {
        "",
        "insufficient",
        "unknown",
        "not applicable",
        "not_applicable",
        "not-applicable",
        "unavailable",
    }


def _confidence_cap(
    *,
    evidence_total: int,
    required_layers: list[str],
    missing_required: list[str],
    blockers: list[str],
    evidence_counts: Counter[str],
) -> float:
    if evidence_total == 0:
        return 0.20
    if any(item.startswith("binding_legal_evidence_missing") for item in blockers):
        return 0.35
    if missing_required:
        return 0.50
    if blockers:
        return 0.60
    if not required_layers:
        return 0.75
    if all(evidence_counts.get(layer, 0) >= 2 for layer in required_layers):
        return 0.92
    return 0.85


def assess_and_calibrate_grounded_answer(
    request: Any,
    answer: Any,
    evidence: list[Any],
) -> DecisionQualityReport:
    """Validate observable answer quality and calibrate confidence fail-closed."""
    message = str(getattr(request, "message", "") or "")
    allowed_layers = {
        str(layer) for layer in (getattr(request, "layers", None) or [])
    }
    required_layers = [
        layer for layer in infer_required_layers(message) if layer in allowed_layers
    ]

    evidence_counts: Counter[str] = Counter(
        str(getattr(item, "layer", "") or "") for item in evidence
    )
    evidence_ids = {
        str(getattr(item, "id", "") or "") for item in evidence if getattr(item, "id", None)
    }
    binding_legal_count = sum(
        1
        for item in evidence
        if str(getattr(item, "layer", "")) == "legal"
        and str(getattr(item, "authority_level", "")) == "binding"
    )

    blockers: list[str] = []
    warnings: list[str] = []
    missing_required = [
        layer for layer in required_layers if evidence_counts.get(layer, 0) == 0
    ]
    blockers.extend(f"required_{layer}_evidence_missing" for layer in missing_required)
    if "legal" in required_layers and binding_legal_count == 0:
        blockers.append("binding_legal_evidence_missing")

    cited_ids: set[str] = set()
    for layer in _SECTION_BY_LAYER:
        citations = _section_citations(answer, layer)
        invalid = sorted(set(citations) - evidence_ids)
        if invalid:
            blockers.append(f"invalid_{layer}_citation_reference")
        valid_citations = [item for item in citations if item in evidence_ids]
        cited_ids.update(valid_citations)
        status = _section_status(answer, layer)
        if _is_claiming_status(status) and evidence_counts.get(layer, 0) > 0 and not valid_citations:
            blockers.append(f"uncited_{layer}_finding")
        if _is_claiming_status(status) and evidence_counts.get(layer, 0) == 0:
            blockers.append(f"unsupported_{layer}_finding")

    if evidence_ids and not cited_ids:
        warnings.append("retrieved_evidence_not_cited")

    risk = _normalize(getattr(answer, "risk", "unknown"))
    query_requires_review = _contains_any(_normalize(message), HUMAN_REVIEW_TERMS)
    risk_requires_review = risk in {"high", "critical"}
    human_review_required = bool(query_requires_review or risk_requires_review or blockers)

    confidence_before = float(getattr(answer, "confidence", 0.0) or 0.0)
    cap = _confidence_cap(
        evidence_total=len(evidence),
        required_layers=required_layers,
        missing_required=missing_required,
        blockers=blockers,
        evidence_counts=evidence_counts,
    )
    confidence_after = min(max(confidence_before, 0.0), cap)

    setattr(answer, "confidence", confidence_after)
    if human_review_required:
        setattr(answer, "requires_human_review", True)

    required_count = len(required_layers)
    covered_count = required_count - len(missing_required)
    coverage_pct = (
        round(covered_count * 100.0 / required_count, 2)
        if required_count
        else (100.0 if evidence else 0.0)
    )

    return DecisionQualityReport(
        required_layers=required_layers,
        evidence_counts=dict(sorted(evidence_counts.items())),
        binding_legal_count=binding_legal_count,
        cited_evidence_count=len(cited_ids),
        evidence_coverage_pct=coverage_pct,
        evidence_sufficient=not blockers and (bool(evidence) or not required_layers),
        confidence_before=round(confidence_before, 6),
        confidence_after=round(confidence_after, 6),
        confidence_cap=cap,
        human_review_required=human_review_required,
        blockers=list(dict.fromkeys(blockers)),
        warnings=list(dict.fromkeys(warnings)),
    )
