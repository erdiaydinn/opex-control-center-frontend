from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

PII_PATTERNS = (
    re.compile(r"\b\d{11}\b"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?:\+?90\s*)?(?:5\d{2})[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}"),
)


@dataclass(frozen=True)
class DatasetGateResult:
    approved: bool
    reasons: tuple[str, ...]
    content_sha256: str


def gate_training_example(example: dict[str, Any]) -> DatasetGateResult:
    canonical = json.dumps(example, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    reasons: list[str] = []
    messages = example.get("messages")
    if not isinstance(messages, list) or not messages:
        reasons.append("messages_missing")
        text = canonical
    else:
        text = "\n".join(str(item.get("content", "")) for item in messages if isinstance(item, dict))
        roles = {item.get("role") for item in messages if isinstance(item, dict)}
        if "user" not in roles or "assistant" not in roles:
            reasons.append("required_roles_missing")
    if any(pattern.search(text) for pattern in PII_PATTERNS):
        reasons.append("possible_pii_detected")
    metadata = example.get("metadata") or {}
    if metadata.get("contains_legal_claim") and not metadata.get("verified_legal_evidence_ids"):
        reasons.append("legal_claim_without_verified_evidence")
    if metadata.get("human_approved") is not True:
        reasons.append("human_approval_missing")
    return DatasetGateResult(not reasons, tuple(reasons), digest)


def filter_training_dataset(examples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[DatasetGateResult]]:
    approved: list[dict[str, Any]] = []
    results: list[DatasetGateResult] = []
    for example in examples:
        result = gate_training_example(example)
        results.append(result)
        if result.approved:
            approved.append(example)
    return approved, results
