# EAY Multilingual 5x Learning Standard

EAY AI Core treats multilingual capability as a training, retrieval and evaluation property rather than a UI translation feature.

## Core language set

The first mandatory language set is:

- Turkish (`tr`)
- English (`en`)
- German (`de`)
- Arabic (`ar`, RTL)
- Persian/Farsi (`fa`, RTL)

The language registry is intentionally extensible. Additional languages may be added only with their own quality/eval coverage; adding a locale label alone does not make a language production-ready.

## Five-times learning depth

`5x-v1` replaces shallow six-view teaching with thirty distinct pedagogical lenses per concept and per language. A single concept therefore has 30 x 5 = 150 mandatory core curriculum slots before the multilingual depth bundle is complete.

The thirty lenses cover explanation, Q&A, reasoning, error detection/correction, counterexamples, ambiguity and edge cases, concise/detailed/formal/conversational expression, terminology, paraphrase, translation, cross-lingual QA, retrieval/citation grounding, temporal reasoning, tool use, business/retail/legal/KPI scenarios, adversarial prompts, hallucination resistance, abstention and teacher critique/revision.

## Safety rule

Coverage is not acceptance. Every generated slot still has to pass the existing privacy, teacher-quality, grounding, temporal-legal, evidence and human-approval gates. Teacher output cannot enter training merely because the 150-slot curriculum is complete.

`build_learning_depth_plan()` deterministically creates curriculum slots and fingerprints. `evaluate_learning_depth_bundle()` fails closed on missing languages, missing lenses, duplicates or slot-count drift. Training examples that declare `metadata.curriculum_profile = "5x-v1"` are grouped by `concept_id` and must complete the full core bundle before `validate_training_examples()` can accept the dataset.

This structure is designed so EAY learns one canonical concept across languages rather than memorizing unrelated translations. Later phases should bind these concept IDs to multilingual RAG nodes, terminology dictionaries and per-language eval scorecards.
