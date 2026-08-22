from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.cyber_championship_execution import (
    BlindEvaluatorReceipt,
    BlindScoreReceipt,
    ChampionshipSandboxAuthorization,
    CompetitorKind,
    SealedTaskBankReceipt,
    SystemExecutionReceipt,
    assess_cycle,
    blind_score_run,
    classify_failures,
)
from app.cyber_championship_learning import build_lost_domain_remediation_queue


def _load(path: str, model_cls):
    return model_cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank-receipt")
    parser.add_argument("--sandbox-receipt")
    parser.add_argument("--run-receipt", action="append", default=[])
    parser.add_argument("--evaluator-receipt", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    bank = (
        _load(args.bank_receipt, SealedTaskBankReceipt)
        if args.bank_receipt
        else None
    )
    sandbox = (
        _load(args.sandbox_receipt, ChampionshipSandboxAuthorization)
        if args.sandbox_receipt
        else None
    )
    runs = tuple(_load(path, SystemExecutionReceipt) for path in args.run_receipt)
    evaluators = tuple(
        _load(path, BlindEvaluatorReceipt) for path in args.evaluator_receipt
    )

    scores: tuple[BlindScoreReceipt, ...] = ()
    queue = None
    if bank is not None and sandbox is not None and runs:
        evaluator_by_run = {item.run_fingerprint: item for item in evaluators}
        score_list = []
        for run in runs:
            evaluator = evaluator_by_run.get(run.fingerprint)
            if evaluator is None:
                continue
            score_list.append(
                blind_score_run(
                    bank=bank,
                    sandbox=sandbox,
                    run=run,
                    evaluator=evaluator,
                )
            )
        scores = tuple(score_list)

        jarvis_run = next(
            (item for item in runs if item.competitor is CompetitorKind.JARVIS),
            None,
        )
        jarvis_score = next(
            (item for item in scores if item.competitor is CompetitorKind.JARVIS),
            None,
        )
        baseline_scores = tuple(
            item for item in scores if item.competitor is not CompetitorKind.JARVIS
        )
        if (
            jarvis_run is not None
            and jarvis_score is not None
            and len(baseline_scores) == 3
            and jarvis_run.fingerprint in evaluator_by_run
        ):
            summary = classify_failures(
                run=jarvis_run,
                evaluator=evaluator_by_run[jarvis_run.fingerprint],
            )
            queue = build_lost_domain_remediation_queue(
                bank=bank,
                jarvis_score=jarvis_score,
                baseline_scores=baseline_scores,
                jarvis_failure_summary=summary,
                created_at=datetime.now(UTC),
            )

    cycle = assess_cycle(
        bank=bank,
        sandbox=sandbox,
        runs=runs,
        scores=scores,
        remediation_queue=queue,
    )
    report = {
        "contract": cycle.contract,
        "status": cycle.status.value,
        "bank_present": bank is not None,
        "sandbox_present": sandbox is not None,
        "completed_competitors": [item.value for item in cycle.completed_competitors],
        "blind_scores": len(scores),
        "remediation_items": len(queue.items) if queue is not None else 0,
        "blockers": list(cycle.blockers),
        "verified_leader_claim_allowed": cycle.verified_leader_claim_allowed,
        "production_security_superiority_claim_allowed": (
            cycle.production_security_superiority_claim_allowed
        ),
        "secrets_or_ground_truth_printed": False,
    }
    print(json.dumps(report, sort_keys=True))
    if args.strict and cycle.blockers:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
