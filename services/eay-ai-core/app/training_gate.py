from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from .learning_quality import evaluate_learning_example


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

        user_text = "\n".join(
            str(m.get("content", ""))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        )
        assistant_text = "\n".join(
            str(m.get("content", ""))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "assistant"
        )
        assistant_lower = assistant_text.lower()
        metadata = example.get("metadata") or {}
        if not isinstance(metadata, dict):
            violations.append(f"example_{idx}:invalid_metadata")
            continue

        legal_claim = any(
            token in assistant_lower
            for token in ("kanunen", "mevzuata göre", "yasal olarak", "resmî gazete")
        )
        provenance = metadata.get("legal_provenance")
        if legal_claim and not provenance:
            violations.append(f"example_{idx}:legal_claim_without_provenance")
        if metadata.get("human_approved") is not True:
            violations.append(f"example_{idx}:not_human_approved")
        if metadata.get("contains_personal_data") is True:
            violations.append(f"example_{idx}:personal_data_not_allowed")

        evidence_ids: list[str] = []
        if isinstance(provenance, dict):
            evidence_ids = [str(value) for value in provenance.values() if value]
        elif provenance:
            evidence_ids = [str(provenance)]

        quality = evaluate_learning_example(
            user_message=user_text,
            model_answer=str(metadata.get("original_model_answer") or ""),
            target_answer=assistant_text,
            reason=str(metadata.get("reason") or ""),
            teacher_reviewed=metadata.get("teacher_reviewed") is True,
            human_approved=metadata.get("human_approved") is True,
            evidence_ids=evidence_ids,
            legal_claim=legal_claim,
            privacy_safe=metadata.get("contains_personal_data") is not True,
        )
        for item in quality.violations:
            mapped = {
                "human_approval_required": "not_human_approved",
                "privacy_review_required": "personal_data_not_allowed",
                "legal_claim_without_evidence": "legal_claim_without_provenance",
            }.get(item, item)
            violation = f"example_{idx}:{mapped}"
            if violation not in violations:
                violations.append(violation)

    return DatasetGateResult(
        accepted=not violations,
        dataset_sha256=canonical_dataset_sha256(examples),
        example_count=len(examples),
        violations=violations,
    )
