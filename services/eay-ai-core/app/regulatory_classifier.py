from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

SignalClass = Literal[
    "draft_consultation",
    "binding_publication_signal",
    "guidance",
    "committee_activity",
    "unknown_regulatory_signal",
]


class RegulatorySignal(BaseModel):
    classification: SignalClass
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    can_auto_promote_to_binding: bool = False


PATTERNS: list[tuple[SignalClass, float, tuple[str, ...]]] = [
    (
        "draft_consultation",
        0.99,
        (
            r"\bmevzuat\s+tasla[gğ][ıi]\b",
            r"\btaslak\b",
            r"\bkamuoyu\s+g[oö]r[uü][sş][uü]\b",
            r"\bg[oö]r[uü][sş]\s+bildirme\b",
            r"\bson\s+g[oö]r[uü][sş]\s+bildirme\s+tarihi\b",
        ),
    ),
    (
        "binding_publication_signal",
        0.95,
        (
            r"resm[iî]\s+gazete.?de\s+yay[ıi]mland[ıi]",
            r"say[ıi]l[ıi]\s+resm[iî]\s+gazete",
            r"yay[ıi]mlanarak\s+y[uü]r[uü]rl[uü][gğ]e\s+girdi",
        ),
    ),
    (
        "committee_activity",
        0.9,
        (
            r"ulusal\s+g[ıi]da\s+kodeks\s+komisyonu",
            r"kodeks\s+komisyonu\s+toplant",
            r"mevzuat[ıi]n\s+yay[ıi]mlanmas[ıi].*kararla[sş]t[ıi]r[ıi]ld[ıi]",
        ),
    ),
    (
        "guidance",
        0.9,
        (
            r"\bk[ıi]lavuz\b",
            r"\brehber\b",
            r"\buygulama\s+k[ıi]lavuzu\b",
        ),
    ),
]


def classify_regulatory_text(text: str, *, source_role: str | None = None) -> RegulatorySignal:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    reasons: list[str] = []

    # Draft language dominates publication-like wording because draft documents often
    # mention the regulation they intend to amend. This prevents accidental promotion.
    for classification, confidence, patterns in PATTERNS:
        hits = [pattern for pattern in patterns if re.search(pattern, normalized, flags=re.IGNORECASE)]
        if hits:
            reasons.extend(hits)
            return RegulatorySignal(
                classification=classification,
                confidence=confidence,
                reasons=reasons,
                can_auto_promote_to_binding=False,
            )

    if source_role == "guidance":
        return RegulatorySignal(
            classification="guidance",
            confidence=0.8,
            reasons=["source_role=guidance"],
            can_auto_promote_to_binding=False,
        )
    return RegulatorySignal(
        classification="unknown_regulatory_signal",
        confidence=0.4,
        reasons=["no deterministic classification pattern matched"],
        can_auto_promote_to_binding=False,
    )
