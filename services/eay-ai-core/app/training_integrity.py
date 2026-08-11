from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

_TOKEN_RE = re.compile(r"[\wÇĞİÖŞÜçğıöşü-]+", re.UNICODE)


@dataclass(frozen=True)
class TrainingIntegrityResult:
    accepted: bool
    violations: tuple[str, ...]
    example_fingerprints: tuple[str, ...]
    integrity_sha256: str


def _canonical_token(token: str) -> str:
    folded = token.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _normalize_text(value: object) -> str:
    tokens = [_canonical_token(token) for token in _TOKEN_RE.findall(str(value or ""))]
    return " ".join(token for token in tokens if token)


def _example_text(example: dict[str, Any]) -> tuple[str, str]:
    messages = example.get("messages")
    if not isinstance(messages, list):
        return "", ""
    user = "\n".join(
        str(item.get("content", ""))
        for item in messages
        if isinstance(item, dict) and item.get("role") == "user"
    )
    assistant = "\n".join(
        str(item.get("content", ""))
        for item in messages
        if isinstance(item, dict) and item.get("role") == "assistant"
    )
    return _normalize_text(user), _normalize_text(assistant)


def example_fingerprint(example: dict[str, Any]) -> str:
    user, assistant = _example_text(example)
    payload = json.dumps(
        {"user": user, "assistant": assistant},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _shingles(text: str, width: int = 3) -> frozenset[tuple[str, ...]]:
    tokens = text.split()
    if not tokens:
        return frozenset()
    if len(tokens) < width:
        return frozenset({tuple(tokens)})
    return frozenset(tuple(tokens[index : index + width]) for index in range(len(tokens) - width + 1))


def _similarity(left: str, right: str) -> float:
    left_set = _shingles(left)
    right_set = _shingles(right)
    if not left_set or not right_set:
        return 0.0
    union = left_set | right_set
    return len(left_set & right_set) / len(union)


def _near_duplicate(left: dict[str, Any], right: dict[str, Any], *, threshold: float) -> bool:
    left_user, left_assistant = _example_text(left)
    right_user, right_assistant = _example_text(right)
    if not left_user or not right_user or not left_assistant or not right_assistant:
        return False
    user_similarity = _similarity(left_user, right_user)
    answer_similarity = _similarity(left_assistant, right_assistant)
    return user_similarity >= threshold and answer_similarity >= threshold


def validate_dataset_integrity(
    examples: Sequence[dict[str, Any]], *, near_duplicate_threshold: float = 0.90
) -> TrainingIntegrityResult:
    if not 0.0 < near_duplicate_threshold <= 1.0:
        raise ValueError("training_integrity_invalid_threshold")

    violations: list[str] = []
    fingerprints = tuple(example_fingerprint(example) for example in examples)
    seen: dict[str, int] = {}
    for index, fingerprint in enumerate(fingerprints):
        previous = seen.get(fingerprint)
        if previous is not None:
            violations.append(f"example_{index}:exact_duplicate_of_{previous}")
        else:
            seen[fingerprint] = index

    for left_index in range(len(examples)):
        for right_index in range(left_index + 1, len(examples)):
            if fingerprints[left_index] == fingerprints[right_index]:
                continue
            if _near_duplicate(
                examples[left_index],
                examples[right_index],
                threshold=near_duplicate_threshold,
            ):
                violations.append(
                    f"example_{right_index}:near_duplicate_of_{left_index}"
                )

    material = json.dumps(
        {
            "example_fingerprints": list(fingerprints),
            "near_duplicate_threshold": near_duplicate_threshold,
            "violations": violations,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return TrainingIntegrityResult(
        accepted=not violations,
        violations=tuple(violations),
        example_fingerprints=fingerprints,
        integrity_sha256=hashlib.sha256(material.encode("utf-8")).hexdigest(),
    )


def validate_split_leakage(
    train_examples: Sequence[dict[str, Any]],
    eval_examples: Sequence[dict[str, Any]],
    *,
    near_duplicate_threshold: float = 0.90,
) -> tuple[str, ...]:
    if not 0.0 < near_duplicate_threshold <= 1.0:
        raise ValueError("training_integrity_invalid_threshold")

    violations: list[str] = []
    train_fingerprints = [example_fingerprint(item) for item in train_examples]
    eval_fingerprints = [example_fingerprint(item) for item in eval_examples]
    train_index = {fingerprint: index for index, fingerprint in enumerate(train_fingerprints)}

    for eval_index, fingerprint in enumerate(eval_fingerprints):
        if fingerprint in train_index:
            violations.append(
                f"eval_{eval_index}:exact_leakage_from_train_{train_index[fingerprint]}"
            )
            continue
        for train_pos, train_example in enumerate(train_examples):
            if _near_duplicate(
                train_example,
                eval_examples[eval_index],
                threshold=near_duplicate_threshold,
            ):
                violations.append(
                    f"eval_{eval_index}:near_duplicate_leakage_from_train_{train_pos}"
                )
                break
    return tuple(violations)
