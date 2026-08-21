from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

CORE_LANGUAGES: tuple[str, ...] = ("tr", "en", "de", "ar", "fa")
RTL_LANGUAGES: frozenset[str] = frozenset({"ar", "fa"})

# Five-times learning-depth standard: one concept is deliberately taught from thirty
# different pedagogical views instead of repeating a small prompt set. These are stable
# IDs so dataset/eval lineage can bind to the exact curriculum contract.
LEARNING_LENSES: tuple[str, ...] = (
    "plain_explanation",
    "advanced_explanation",
    "direct_qa",
    "reverse_qa",
    "reasoning_application",
    "error_detection",
    "error_correction",
    "counterexample",
    "ambiguity_resolution",
    "edge_case",
    "concise_answer",
    "detailed_answer",
    "formal_register",
    "conversational_register",
    "terminology_precision",
    "paraphrase",
    "translation_faithfulness",
    "cross_lingual_qa",
    "retrieval_grounding",
    "citation_grounding",
    "temporal_reasoning",
    "tool_use",
    "business_scenario",
    "retail_scenario",
    "legal_scenario",
    "kpi_scenario",
    "adversarial_prompt",
    "hallucination_resistance",
    "abstention_when_uncertain",
    "teacher_critique_and_revision",
)

LEARNING_DEPTH_VERSION = "5x-v1"
EXPECTED_LENSES_PER_LANGUAGE = 30
EXPECTED_CORE_SLOTS = len(CORE_LANGUAGES) * EXPECTED_LENSES_PER_LANGUAGE


@dataclass(frozen=True)
class LearningSlot:
    concept_id: str
    language: str
    lens: str
    rtl: bool
    slot_fingerprint: str


@dataclass(frozen=True)
class LearningDepthPlan:
    concept_id: str
    version: str
    languages: tuple[str, ...]
    lens_count: int
    slot_count: int
    slots: tuple[LearningSlot, ...]
    curriculum_fingerprint: str


@dataclass(frozen=True)
class LearningDepthEval:
    accepted: bool
    expected_slots: int
    observed_slots: int
    missing_languages: tuple[str, ...]
    missing_lenses_by_language: tuple[tuple[str, tuple[str, ...]], ...]
    duplicate_pairs: tuple[str, ...]
    fingerprint: str


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_language(language: str) -> str:
    value = language.strip().lower().replace("_", "-")
    return value.split("-", 1)[0]


def build_learning_depth_plan(
    *,
    concept_id: str,
    languages: Iterable[str] = CORE_LANGUAGES,
) -> LearningDepthPlan:
    concept_id = concept_id.strip()
    if len(concept_id) < 2:
        raise ValueError("learning_concept_id_required")

    normalized_languages = tuple(dict.fromkeys(_normalize_language(item) for item in languages if item.strip()))
    if not normalized_languages:
        raise ValueError("learning_languages_required")
    if len(LEARNING_LENSES) != EXPECTED_LENSES_PER_LANGUAGE:
        raise RuntimeError("learning_depth_contract_lens_count_drift")

    slots: list[LearningSlot] = []
    for language in normalized_languages:
        for lens in LEARNING_LENSES:
            slot_payload = {
                "version": LEARNING_DEPTH_VERSION,
                "concept_id": concept_id,
                "language": language,
                "lens": lens,
            }
            slots.append(
                LearningSlot(
                    concept_id=concept_id,
                    language=language,
                    lens=lens,
                    rtl=language in RTL_LANGUAGES,
                    slot_fingerprint=_sha256(slot_payload),
                )
            )

    curriculum_payload = {
        "version": LEARNING_DEPTH_VERSION,
        "concept_id": concept_id,
        "languages": list(normalized_languages),
        "lenses": list(LEARNING_LENSES),
        "slot_fingerprints": [slot.slot_fingerprint for slot in slots],
    }
    return LearningDepthPlan(
        concept_id=concept_id,
        version=LEARNING_DEPTH_VERSION,
        languages=normalized_languages,
        lens_count=len(LEARNING_LENSES),
        slot_count=len(slots),
        slots=tuple(slots),
        curriculum_fingerprint=_sha256(curriculum_payload),
    )


def evaluate_learning_depth_bundle(
    *,
    concept_id: str,
    observed_pairs: Iterable[tuple[str, str]],
    required_languages: Iterable[str] = CORE_LANGUAGES,
) -> LearningDepthEval:
    """Fail closed unless every required language contains all thirty distinct lenses.

    This gate measures curriculum coverage only; content still has to pass privacy,
    teacher-quality, grounding, legal-temporal and human-approval gates separately.
    """

    required = tuple(dict.fromkeys(_normalize_language(item) for item in required_languages if item.strip()))
    pairs = [(_normalize_language(language), lens.strip()) for language, lens in observed_pairs]
    seen: set[tuple[str, str]] = set()
    duplicates: list[str] = []
    for pair in pairs:
        if pair in seen:
            duplicates.append(f"{pair[0]}:{pair[1]}")
        seen.add(pair)

    missing_languages = tuple(language for language in required if not any(pair[0] == language for pair in seen))
    missing_lenses: list[tuple[str, tuple[str, ...]]] = []
    required_lenses = set(LEARNING_LENSES)
    for language in required:
        observed_lenses = {lens for lang, lens in seen if lang == language}
        missing = tuple(sorted(required_lenses - observed_lenses))
        if missing:
            missing_lenses.append((language, missing))

    expected_slots = len(required) * len(LEARNING_LENSES)
    relevant_seen = {(lang, lens) for lang, lens in seen if lang in required and lens in required_lenses}
    accepted = not missing_languages and not missing_lenses and not duplicates and len(relevant_seen) == expected_slots
    payload = {
        "version": LEARNING_DEPTH_VERSION,
        "concept_id": concept_id.strip(),
        "required_languages": list(required),
        "observed_pairs": sorted([list(pair) for pair in relevant_seen]),
        "duplicates": sorted(duplicates),
    }
    return LearningDepthEval(
        accepted=accepted,
        expected_slots=expected_slots,
        observed_slots=len(relevant_seen),
        missing_languages=missing_languages,
        missing_lenses_by_language=tuple(missing_lenses),
        duplicate_pairs=tuple(sorted(duplicates)),
        fingerprint=_sha256(payload),
    )
