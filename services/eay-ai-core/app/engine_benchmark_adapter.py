"""Benchmark-only adapter from EngineGateway candidates to BenchmarkSystemAdapter.

The adapter is intentionally reasoning-only. It can measure an exact adapter
candidate before production promotion, but cannot enable provider tools or side
effects. Model output is transiently supplied to the evaluator and an external
evidence writer; the benchmark result itself retains only evidence references.
"""

from __future__ import annotations

from typing import Callable

from .benchmark_runner import (
    BenchmarkCaseOutcome,
    BenchmarkEnvironmentManifest,
    BenchmarkSystemAdapter,
    BenchmarkTaskCase,
    BenchmarkTaskSuite,
)
from .engine_gateway import (
    BenchmarkInvocationContext,
    EngineGateway,
    EngineInvocationReceipt,
)
from .intelligence_router import IntelligenceTask

ENGINE_BENCHMARK_ADAPTER_CONTRACT = "eay-engine-benchmark-adapter-v1"


BenchmarkTaskFactory = Callable[[BenchmarkTaskCase], IntelligenceTask]
BenchmarkReceiptEvaluator = Callable[
    [BenchmarkTaskCase, EngineInvocationReceipt], BenchmarkCaseOutcome
]
BenchmarkReceiptEvidenceWriter = Callable[
    [BenchmarkTaskCase, EngineInvocationReceipt], str
]


def build_gateway_reasoning_benchmark_adapter(
    *,
    gateway: EngineGateway,
    engine_id: str,
    system_version: str,
    suite: BenchmarkTaskSuite,
    environment: BenchmarkEnvironmentManifest,
    benchmark_run_ref: str,
    task_factory: BenchmarkTaskFactory,
    evaluator: BenchmarkReceiptEvaluator,
    receipt_evidence_writer: BenchmarkReceiptEvidenceWriter,
) -> BenchmarkSystemAdapter:
    """Create a same-task benchmark adapter for one exact gateway engine."""

    if not engine_id.strip() or not system_version.strip():
        raise ValueError("engine_benchmark_adapter_identity_required")

    async def invoke(case: BenchmarkTaskCase) -> BenchmarkCaseOutcome:
        task = task_factory(case)
        if task.task_id != case.case_id:
            raise ValueError("engine_benchmark_task_id_must_match_case_id")
        context = BenchmarkInvocationContext(
            benchmark_run_ref=benchmark_run_ref,
            engine_id=engine_id,
            task_set_fingerprint=suite.fingerprint(),
            environment_fingerprint=environment.fingerprint(),
            evaluator_ref=case.expected_evaluator_ref,
        )
        receipt = await gateway.invoke_for_benchmark(
            engine_id=engine_id,
            task=task,
            prompt=case.prompt,
            context=context,
        )
        invocation_evidence_ref = receipt_evidence_writer(case, receipt)
        if not invocation_evidence_ref.strip():
            raise ValueError("engine_benchmark_receipt_evidence_ref_required")
        evaluated = evaluator(case, receipt)
        evidence_refs = tuple(
            dict.fromkeys((invocation_evidence_ref, *evaluated.evidence_refs))
        )
        return evaluated.model_copy(update={"evidence_refs": evidence_refs})

    return BenchmarkSystemAdapter(
        system_id=engine_id,
        system_version=system_version,
        invoke=invoke,
    )
