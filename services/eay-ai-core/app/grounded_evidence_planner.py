"""Observable, deterministic evidence planning for grounded Jarvis retrieval.

The planner is not chain-of-thought. It converts the user-visible question and
allowed authority layers into a bounded retrieval contract: target layers,
query variants, purposes and execution counts. Facts still come only from the
retrieval store and later evidence/critic guards.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from .grounded_reasoning import infer_required_layers

EVIDENCE_PLAN_CONTRACT = "grounded-evidence-plan-v1"
MAX_EVIDENCE_QUERIES = 4

KnowledgeLayer = Literal["legal", "company", "standard", "operational"]
_LAYER_ORDER: tuple[KnowledgeLayer, ...] = (
    "legal",
    "company",
    "standard",
    "operational",
)
_TOKEN_RE = re.compile(r"[\wÇĞİÖŞÜçğıöşü-]{2,}", re.UNICODE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "bu",
    "bir",
    "da",
    "de",
    "for",
    "ile",
    "in",
    "is",
    "mi",
    "mı",
    "mu",
    "mü",
    "ne",
    "nedir",
    "nasil",
    "nasıl",
    "of",
    "olan",
    "olarak",
    "the",
    "to",
    "ve",
    "what",
    "which",
    "with",
}
_COMPLEX_MARKERS = {
    "why",
    "neden",
    "root cause",
    "kök neden",
    "kok neden",
    "compare",
    "karşılaştır",
    "karsilastir",
    "recommend",
    "öner",
    "oner",
    "scenario",
    "senaryo",
    "risk",
    "forecast",
    "tahmin",
}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text).strip()


def _norm_key(value: str) -> str:
    return _norm(value).casefold().replace("ı", "i")


def _allowed_layers(request: Any) -> list[KnowledgeLayer]:
    requested = [str(item) for item in (getattr(request, "layers", None) or [])]
    return [layer for layer in _LAYER_ORDER if layer in requested]


def _distilled_query(message: str) -> str:
    tokens = _TOKEN_RE.findall(message)
    selected: list[str] = []
    for token in tokens:
        normalized = _norm_key(token)
        if normalized in _STOPWORDS:
            continue
        if normalized not in {_norm_key(item) for item in selected}:
            selected.append(token)
        if len(selected) >= 12:
            break
    return " ".join(selected)


def _clause_queries(message: str) -> list[str]:
    parts = re.split(
        r"[?;]+|\s+(?:ve|and|ayrica|ayrıca|but|ancak)\s+",
        message,
        flags=re.IGNORECASE,
    )
    output: list[str] = []
    for part in parts:
        candidate = _distilled_query(part)
        if len(_TOKEN_RE.findall(candidate)) >= 2:
            output.append(candidate)
    return output


def _acronym_query(message: str) -> str:
    tokens = re.findall(r"\b[A-Z][A-Z0-9_-]{1,11}\b", message)
    unique = list(dict.fromkeys(tokens))
    return " ".join(unique[:8])


class EvidenceQueryStep(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    layers: list[KnowledgeLayer] = Field(min_length=1, max_length=4)
    purpose: Literal["primary", "layer_focus", "clause", "acronym_focus"]
    limit: int = Field(ge=1, le=32)


class EvidencePlan(BaseModel):
    contract: str = EVIDENCE_PLAN_CONTRACT
    strategy: str = "deterministic-diversified-retrieval-v1"
    allowed_layers: list[KnowledgeLayer] = Field(default_factory=list)
    inferred_required_layers: list[KnowledgeLayer] = Field(default_factory=list)
    active_layers: list[KnowledgeLayer] = Field(default_factory=list)
    steps: list[EvidenceQueryStep] = Field(default_factory=list, max_length=MAX_EVIDENCE_QUERIES)
    legal_temporal_resolution_required: bool = False
    candidate_count: int = 0
    selected_count: int = 0
    selected_layer_counts: dict[str, int] = Field(default_factory=dict)


def _step_limit(base_limit: int, layers: list[KnowledgeLayer]) -> int:
    if "legal" in layers:
        return min(max(base_limit * 4, base_limit), 32)
    return min(max(base_limit * 2, base_limit), 24)


def build_evidence_plan(request: Any, base_limit: int) -> EvidencePlan:
    message = _norm(getattr(request, "message", ""))
    allowed = _allowed_layers(request)
    inferred = [
        layer
        for layer in infer_required_layers(message)
        if layer in allowed
    ]
    active = inferred or allowed
    if not active or not message:
        return EvidencePlan(
            allowed_layers=allowed,
            inferred_required_layers=inferred,
            active_layers=active,
        )

    steps: list[EvidenceQueryStep] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    def add(query: str, layers: list[KnowledgeLayer], purpose: str) -> None:
        if len(steps) >= MAX_EVIDENCE_QUERIES:
            return
        query = _norm(query)
        if not query or not layers:
            return
        key = (_norm_key(query), tuple(layers))
        if key in seen:
            return
        seen.add(key)
        steps.append(
            EvidenceQueryStep(
                query=query,
                layers=layers,
                purpose=purpose,
                limit=_step_limit(base_limit, layers),
            )
        )

    add(message, active, "primary")

    # Diversify by authority layer only when the question itself explicitly
    # requires multiple layers. Ambiguous questions preserve the caller's
    # allowed retrieval window without inventing extra layer-focused intent.
    if len(inferred) > 1:
        for layer in inferred:
            add(message, [layer], "layer_focus")

    normalized_message = _norm_key(message)
    if any(_norm_key(marker) in normalized_message for marker in _COMPLEX_MARKERS):
        distilled = _distilled_query(message)
        if distilled and _norm_key(distilled) != normalized_message:
            add(distilled, active, "clause")
        for clause in _clause_queries(message):
            add(clause, active, "clause")

    acronym = _acronym_query(message)
    if acronym and _norm_key(acronym) != normalized_message:
        add(acronym, active, "acronym_focus")

    return EvidencePlan(
        allowed_layers=allowed,
        inferred_required_layers=inferred,
        active_layers=active,
        steps=steps,
        legal_temporal_resolution_required=any(
            "legal" in step.layers for step in steps
        ),
    )


def execute_evidence_plan(
    plan: EvidencePlan,
    *,
    store: Any,
    as_of: Any,
) -> list[Any]:
    candidates: dict[str, Any] = {}
    first_seen: dict[str, int] = {}
    sequence = 0
    for step in plan.steps:
        rows = store.search(step.query, as_of, step.layers, step.limit)
        for row in rows:
            evidence_id = str(getattr(row, "id", "") or "")
            if not evidence_id:
                continue
            sequence += 1
            first_seen.setdefault(evidence_id, sequence)
            current = candidates.get(evidence_id)
            if current is None or float(getattr(row, "score", 0.0) or 0.0) > float(
                getattr(current, "score", 0.0) or 0.0
            ):
                candidates[evidence_id] = row
    plan.candidate_count = len(candidates)
    return sorted(
        candidates.values(),
        key=lambda row: (
            -float(getattr(row, "score", 0.0) or 0.0),
            first_seen.get(str(getattr(row, "id", "") or ""), 10**9),
            str(getattr(row, "id", "") or ""),
        ),
    )


def select_evidence(
    plan: EvidencePlan,
    candidates: list[Any],
    *,
    limit: int,
) -> list[Any]:
    if limit <= 0:
        plan.selected_count = 0
        plan.selected_layer_counts = {}
        return []

    selected: list[Any] = []
    selected_ids: set[str] = set()

    def add(row: Any) -> None:
        evidence_id = str(getattr(row, "id", "") or "")
        if not evidence_id or evidence_id in selected_ids or len(selected) >= limit:
            return
        selected_ids.add(evidence_id)
        selected.append(row)

    # Guarantee one best candidate per explicitly required layer before filling
    # the remaining score-ranked window. Missing layers remain visible to the
    # deterministic decision-quality guard rather than being invented here.
    for layer in plan.inferred_required_layers:
        row = next(
            (item for item in candidates if str(getattr(item, "layer", "")) == layer),
            None,
        )
        if row is not None:
            add(row)

    for row in candidates:
        add(row)

    counts = Counter(str(getattr(row, "layer", "") or "") for row in selected)
    plan.selected_count = len(selected)
    plan.selected_layer_counts = dict(sorted(counts.items()))
    return selected
