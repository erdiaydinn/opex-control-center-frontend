from app.multilingual_learning import CORE_LANGUAGES, LEARNING_DEPTH_VERSION, LEARNING_LENSES
from app.training_gate import validate_training_examples


def _example(language: str, lens: str, index: int):
    return {
        "messages": [
            {
                "role": "user",
                "content": f"Explain operational concept {index} in language {language} using lens {lens}.",
            },
            {
                "role": "assistant",
                "content": (
                    f"For curriculum slot {index}, the {lens} view explains the operational concept "
                    f"with explicit assumptions, a concrete decision rule, a verification step, and a "
                    f"clear uncertainty boundary for language {language}."
                ),
            },
        ],
        "metadata": {
            "human_approved": True,
            "contains_personal_data": False,
            "teacher_reviewed": True,
            "teacher_quality_accepted": True,
            "teacher_quality_sha256": f"{(index % 10)}" * 64,
            "reason": "reviewed multilingual learning-depth curriculum",
            "curriculum_profile": LEARNING_DEPTH_VERSION,
            "concept_id": "inventory-accuracy",
            "language": language,
            "learning_lens": lens,
        },
    }


def test_training_gate_rejects_old_six_lens_depth_when_5x_profile_is_declared():
    examples = []
    index = 0
    for language in CORE_LANGUAGES:
        for lens in LEARNING_LENSES[:6]:
            examples.append(_example(language, lens, index))
            index += 1

    result = validate_training_examples(examples)
    assert result.accepted is False
    assert result.learning_depth_fingerprints
    assert any("learning_depth:slot_count:30/150" in item for item in result.violations)
    assert any("learning_depth:tr:missing_lenses" in item for item in result.violations)
