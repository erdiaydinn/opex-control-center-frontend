"""Local-first adaptive teaching runtime for EAY Jarvis.

Teaching content is generated from an evidence-bound learning objective and an
explicit teaching move. The runtime never treats model output as hidden
reasoning or self-attested truth. It sends only the minimum ephemeral grounded
context needed for the step and delegates inference to the existing
``LocalFirstProductionRuntime``:

1. use a benchmarked, reachable local specialist when available;
2. otherwise enter the existing admin-governed paid-frontier path;
3. never let a teaching request itself authorize paid spend or external data
   processing.

Raw grounded excerpts and learner responses are intentionally absent from the
receipt. The durable receipt keeps only source references, generated teaching
content and the governed inference receipt.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .intelligence_router import (
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from .local_first_engine_runtime import LocalFirstInvocationReceipt, LocalFirstProductionRuntime
from .local_model_pool import LocalCapability, LocalModelTask
from .paid_token_engine_gateway import PaidTokenExecutionContext
from .teaching_intelligence import LearningObjective, TeachingMove

TEACHING_RUNTIME_CONTRACT = "eay-teaching-runtime-v1"


class TeachingGenerationKind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    EXPLANATION = "explanation"
    WORKED_EXAMPLE = "worked_example"
    CONTRASTIVE_EXAMPLE = "contrastive_example"
    RETRIEVAL_QUESTION = "retrieval_question"
    TEACH_BACK_PROMPT = "teach_back_prompt"
    TRANSFER_CHALLENGE = "transfer_challenge"
    CORRECTIVE_FEEDBACK = "corrective_feedback"
    SPACED_REVIEW = "spaced_review"


_MOVE_KIND = {
    TeachingMove.DIAGNOSTIC: TeachingGenerationKind.DIAGNOSTIC,
    TeachingMove.EXPLAIN: TeachingGenerationKind.EXPLANATION,
    TeachingMove.WORKED_EXAMPLE: TeachingGenerationKind.WORKED_EXAMPLE,
    TeachingMove.CONTRASTIVE_EXAMPLE: TeachingGenerationKind.CONTRASTIVE_EXAMPLE,
    TeachingMove.RETRIEVAL_PRACTICE: TeachingGenerationKind.RETRIEVAL_QUESTION,
    TeachingMove.TEACH_BACK: TeachingGenerationKind.TEACH_BACK_PROMPT,
    TeachingMove.TRANSFER_CHALLENGE: TeachingGenerationKind.TRANSFER_CHALLENGE,
    TeachingMove.FEEDBACK: TeachingGenerationKind.CORRECTIVE_FEEDBACK,
    TeachingMove.SPACED_REVIEW: TeachingGenerationKind.SPACED_REVIEW,
}


class TeachingGenerationRequest(BaseModel):
    learner_ref: str = Field(min_length=1)
    objective: LearningObjective
    move: TeachingMove
    preferred_language: str = Field(min_length=2)
    privacy: PrivacyLevel = PrivacyLevel.INTERNAL
    external_processing_authorized: bool = False
    minimum_local_benchmark_score: float = Field(default=0.80, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def request_has_grounded_objective(self) -> "TeachingGenerationRequest":
        if not self.objective.source_refs:
            raise ValueError("teaching_runtime_objective_sources_required")
        return self


class TeachingArtifactReceipt(BaseModel):
    contract: str = TEACHING_RUNTIME_CONTRACT
    learner_ref: str
    objective_id: str
    move: TeachingMove
    kind: TeachingGenerationKind
    preferred_language: str
    source_refs: tuple[str, ...]
    content: str = Field(min_length=1)
    inference: LocalFirstInvocationReceipt
    source_gap_detected: bool = False
    prompt_retained: bool = False
    grounded_context_retained: bool = False
    learner_response_retained: bool = False
    hidden_reasoning_requested: bool = False

    @model_validator(mode="after")
    def receipt_is_secret_and_reasoning_safe(self) -> "TeachingArtifactReceipt":
        if self.prompt_retained or self.grounded_context_retained or self.learner_response_retained:
            raise ValueError("teaching_runtime_receipt_cannot_retain_raw_input")
        if self.hidden_reasoning_requested:
            raise ValueError("teaching_runtime_never_requests_hidden_reasoning")
        return self


def _complexity(move: TeachingMove) -> TaskComplexity:
    if move in {
        TeachingMove.CONTRASTIVE_EXAMPLE,
        TeachingMove.TRANSFER_CHALLENGE,
        TeachingMove.FEEDBACK,
    }:
        return TaskComplexity.HARD
    return TaskComplexity.STANDARD


def _task_class(move: TeachingMove) -> str:
    if move is TeachingMove.FEEDBACK:
        return "TEACHING_FEEDBACK"
    if move is TeachingMove.TRANSFER_CHALLENGE:
        return "TEACHING_TRANSFER"
    return "TEACHING"


def _build_prompt(
    *,
    request: TeachingGenerationRequest,
    grounded_context: str,
    learner_response: str | None,
) -> str:
    if not grounded_context.strip():
        raise ValueError("teaching_runtime_grounded_context_required")
    if request.move is TeachingMove.FEEDBACK and not (learner_response or "").strip():
        raise ValueError("teaching_runtime_feedback_requires_learner_response")
    if request.move is not TeachingMove.FEEDBACK and learner_response is not None:
        raise ValueError("teaching_runtime_learner_response_only_allowed_for_feedback")

    instructions = [
        "You are EAY Jarvis Teacher.",
        "Use only the supplied grounded context for factual claims.",
        "Do not reveal or request hidden chain-of-thought; provide only the teaching artifact.",
        "If the grounded context is insufficient for a factual claim, start the answer with SOURCE_GAP.",
        "Do not invent citations, policies, numbers, definitions, company rules or legal claims.",
        f"Language: {request.preferred_language}",
        f"Teaching move: {request.move.value}",
        f"Objective: {request.objective.title}",
        f"Domain: {request.objective.domain}",
        "Grounded context follows:",
        grounded_context.strip(),
    ]
    if learner_response is not None:
        instructions.extend(
            [
                "Learner response follows. Diagnose the misconception without quoting the response verbatim.",
                learner_response.strip(),
            ]
        )
    return "\n\n".join(instructions)


def _output_text(receipt: LocalFirstInvocationReceipt) -> str:
    if receipt.local_receipt is not None:
        return receipt.local_receipt.output_text.strip()
    if receipt.frontier_receipt is None:
        raise RuntimeError("teaching_runtime_inference_receipt_missing")
    return receipt.frontier_receipt.engine_receipt.output_text.strip()


async def generate_teaching_artifact(
    *,
    runtime: LocalFirstProductionRuntime,
    request: TeachingGenerationRequest,
    grounded_context: str,
    context: PaidTokenExecutionContext,
    learner_response: str | None = None,
) -> TeachingArtifactReceipt:
    """Generate one teaching artifact through the governed local-first runtime.

    ``grounded_context`` and ``learner_response`` are ephemeral call inputs and
    are intentionally not copied into the durable receipt. Paid escalation is
    never authorized here; the existing platform-admin grant/rate-card/budget
    layer remains authoritative if no local specialist qualifies.
    """

    prompt = _build_prompt(
        request=request,
        grounded_context=grounded_context,
        learner_response=learner_response,
    )
    local_task = LocalModelTask(
        task_ref=(
            f"teaching:{request.learner_ref}:{request.objective.objective_id}:"
            f"{request.move.value}"
        ),
        task_class=_task_class(request.move),
        required_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.REASONING}),
        minimum_benchmark_score=request.minimum_local_benchmark_score,
    )
    intelligence_task = IntelligenceTask(
        task_id=local_task.task_ref,
        complexity=_complexity(request.move),
        risk=TaskRisk.LOW,
        privacy=request.privacy,
        modalities=(Modality.TEXT,),
        requires_tools=False,
        requires_long_horizon=False,
        external_processing_authorized=request.external_processing_authorized,
        requires_independent_critique=False,
    )
    inference = await runtime.invoke_primary(
        local_task=local_task,
        task=intelligence_task,
        prompt=prompt,
        context=context,
    )
    content = _output_text(inference)
    if not content:
        raise RuntimeError("teaching_runtime_generated_content_missing")

    if learner_response is not None:
        raw = learner_response.strip()
        if len(raw) >= 16 and raw.casefold() in content.casefold():
            raise RuntimeError("teaching_runtime_raw_learner_response_echo_forbidden")

    return TeachingArtifactReceipt(
        learner_ref=request.learner_ref,
        objective_id=request.objective.objective_id,
        move=request.move,
        kind=_MOVE_KIND[request.move],
        preferred_language=request.preferred_language,
        source_refs=request.objective.source_refs,
        content=content,
        inference=inference,
        source_gap_detected=content.lstrip().upper().startswith("SOURCE_GAP"),
    )
