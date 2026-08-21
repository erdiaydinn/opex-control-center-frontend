from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from .learning_quality import evaluate_learning_example
from .multilingual_learning import LEARNING_DEPTH_VERSION, evaluate_learning_depth_bundle
from .privacy_guard import scan_personal_data
from .training_integrity import validate_dataset_integrity


class DatasetGateResult(BaseModel):
    accepted: bool
    dataset_sha256: str
    example_count: int
    violations: list[str] = Field(default_factory=list)
    quality_fingerprints: list[str] = Field(default_factory=list)
    teacher_quality_fingerprints: list[str] = Field(default_factory=list)
    learning_depth_fingerprints: list[str] = Field(default_factory=list)
    integrity_sha256: str | None = None


def canonical_dataset_sha256(examples: list[dict[str, Any]]) -> str:
    payload = json.dumps(examples, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _iter_text_values(value: object) -> Iterable[str]:
    """Yield string leaves without serializing/copying the whole example into logs."""

    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_text_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_text_values(item)


def validate_training_examples(examples: list[dict[str, Any]]) -> DatasetGateResult:
    violations: list[str] = []
    quality_fingerprints: list[str] = []
    teacher_quality_fingerprints: list[str] = []
    learning_depth_fingerprints: list[str] = []
    curriculum_pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    curriculum_indexes: dict[str, list[int]] = defaultdict(list)
    if not examples:
        violations.append("empty_dataset")

    for idx, example in enumerate(examples):
        privacy = scan_personal_data(_iter_text_values(example))
        for kind in privacy.kinds:
            violations.append(f"example_{idx}:personal_data_detected:{kind}")

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

        curriculum_profile = str(metadata.get("curriculum_profile") or "").strip()
        if curriculum_profile:
            if curriculum_profile != LEARNING_DEPTH_VERSION:
                violations.append(f"example_{idx}:unsupported_curriculum_profile")
            else:
                concept_id = str(metadata.get("concept_id") or "").strip()
                language = str(metadata.get("language") or "").strip()
                learning_lens = str(metadata.get("learning_lens") or "").strip()
                if not concept_id:
                    violations.append(f"example_{idx}:curriculum_concept_id_required")
                if not language:
                    violations.append(f"example_{idx}:curriculum_language_required")
                if not learning_lens:
                    violations.append(f"example_{idx}:curriculum_learning_lens_required")
                if concept_id and language and learning_lens:
                    curriculum_pairs[concept_id].append((language, learning_lens))
                    curriculum_indexes[concept_id].append(idx)

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

        teacher_reviewed = metadata.get("teacher_reviewed") is True
        if teacher_reviewed:
            if metadata.get("teacher_quality_accepted") is not True:
                violations.append(f"example_{idx}:teacher_quality_not_accepted")
            teacher_fp = metadata.get("teacher_quality_sha256")
            if not _is_sha256(teacher_fp):
                violations.append(f"example_{idx}:teacher_quality_fingerprint_required")
            else:
                teacher_quality_fingerprints.append(str(teacher_fp))

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
            teacher_reviewed=teacher_reviewed,
            human_approved=metadata.get("human_approved") is True,
            evidence_ids=evidence_ids,
            legal_claim=legal_claim,
            privacy_safe=metadata.get("contains_personal_data") is not True and privacy.safe,
        )
        quality_fingerprints.append(quality.target_sha256)
        for item in quality.violations:
            mapped = {
                "human_approval_required": "not_human_approved",
                "privacy_review_required": "personal_data_not_allowed",
                "legal_claim_without_evidence": "legal_claim_without_provenance",
            }.get(item, item)
            violation = f"example_{idx}:{mapped}"
            if violation not in violations:
                violations.append(violation)

    for concept_id, observed_pairs in sorted(curriculum_pairs.items()):
        depth = evaluate_learning_depth_bundle(concept_id=concept_id, observed_pairs=observed_pairs)
        learning_depth_fingerprints.append(depth.fingerprint)
        if not depth.accepted:
            prefix = f"concept_{concept_id}:learning_depth"
            if depth.missing_languages:
                violations.append(prefix + ":missing_languages:" + ",".join(depth.missing_languages))
            for language, missing in depth.missing_lenses_by_language:
                violations.append(prefix + f":{language}:missing_lenses:" + ",".join(missing))
            if depth.duplicate_pairs:
                violations.append(prefix + ":duplicate_pairs:" + ",".join(depth.duplicate_pairs))
            if depth.observed_slots != depth.expected_slots:
                violations.append(
                    prefix + f":slot_count:{depth.observed_slots}/{depth.expected_slots}"
                )

    integrity = validate_dataset_integrity(examples)
    for item in integrity.violations:
        if item not in violations:
            violations.append(item)

    return DatasetGateResult(
        accepted=not violations,
        dataset_sha256=canonical_dataset_sha256(examples),
        example_count=len(examples),
        violations=violations,
        quality_fingerprints=quality_fingerprints,
        teacher_quality_fingerprints=teacher_quality_fingerprints,
        learning_depth_fingerprints=learning_depth_fingerprints,
        integrity_sha256=integrity.integrity_sha256,
    )
