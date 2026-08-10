from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


class DatasetGateResult(BaseModel):
    accepted: bool
    dataset_sha256: str
    example_count: int
    violations: list[str] = Field(default_factory=list)


def canonical_dataset_sha256(examples: list[dict[str, Any]]) -> str:
    payload = json.dumps(examples, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_training_examples(examples: list[dict[str, Any]]) -> DatasetGateResult:
    violations: list[str] = []
    if not examples:
        violations.append("empty_dataset")

    for idx, example in enumerate(examples):
        messages = example.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            violations.append(f"example_{idx}:invalid_messages")
            continue
        roles = [m.get("role") for m in messages if isinstance(m, dict)]
        if "user" not in roles or "assistant" not in roles:
            violations.append(f"example_{idx}:missing_user_or_assistant")
        assistant_text = "\n".join(
            str(m.get("content", "")) for m in messages
            if isinstance(m, dict) and m.get("role") == "assistant"
        ).lower()
        metadata = example.get("metadata") or {}
        if any(token in assistant_text for token in ("kanunen", "mevzuata göre", "yasal olarak", "resmî gazete")):
            provenance = metadata.get("legal_provenance")
            if not provenance:
                violations.append(f"example_{idx}:legal_claim_without_provenance")
        if metadata.get("human_approved") is not True:
            violations.append(f"example_{idx}:not_human_approved")
        if metadata.get("contains_personal_data") is True:
            violations.append(f"example_{idx}:personal_data_not_allowed")

    return DatasetGateResult(
        accepted=not violations,
        dataset_sha256=canonical_dataset_sha256(examples),
        example_count=len(examples),
        violations=violations,
    )
