from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import app.cyber_championship_execution as execution
import app.cyber_championship_vendor_adapters as vendor
from app.cyber_benchmark_intelligence import CyberBenchmarkEvidenceClass
from app.cyber_championship_execution import (
    BlindEvaluatorReceipt,
    ChampionshipCycleStatus,
    ChampionshipSandboxAuthorization,
    ChampionshipTrack,
    CompetitorKind,
    EvaluatedTaskResult,
    FailureClass,
    SealedTaskBankReceipt,
    SystemExecutionReceipt,
    assess_cycle,
    authorize_retest_rotation,
    blind_score_run,
    build_remediation_queue,
    classify_failures,
)
from app.cyber_championship_vendor_adapters import (
    CompetitorRunnerAuthorization,
    RunnerAuthorityStatus,
    assess_runner_authority,
    default_competitor_adapter_specs,
    execute_real_competitor_run,
)

NOW = datetime(2026, 8, 22, 5, 45, tzinfo=UTC)
ENVIRONMENT = "1" * 64


def _bank(*, rotation: str = "rotation-001", task_hash: str = "2" * 64, truth_hash: str = "3" * 64):
    return execution._seal_model(
        SealedTaskBankReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "bank_id": "independent-bank-2026-08",
            "rotation_epoch": rotation,
            "task_set_fingerprint": task_hash,
            "public_manifest_sha256": "4" * 64,
            "sealed_ground_truth_sha256": truth_hash,
            "task_count": 110,
            "tracks": tuple(ChampionshipTrack),
            "independent_provider_ref": "evidence://independent-evaluator/bank-2026-08",
            "sealed_storage_ref": "sealed://evaluator-vault/bank-2026-08",
            "evaluator_key_id": "evaluator-key-2026-08",
            "issued_at": NOW,
            "expires_at": NOW + timedelta(days=7),
            "ground_truth_embedded_in_repository": False,
            "ground_truth_visible_to_competitors": False,
            "bank_mutable_after_issue": False,
        },
    )


def _sandbox():
    return execution._seal_model(
        ChampionshipSandboxAuthorization,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "sandbox_id": "cyber-championship-sandbox-001",
            "environment_fingerprint": ENVIRONMENT,
            "evidence_class": CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
            "authorization_evidence_ref": "evidence://security-guardian/sandbox-001",
            "worker_attestation_refs": ("attestation://worker/jarvis-001",),
            "network_policy_ref": "policy://championship-deny-default-v1",
            "workload_identity_ref": "identity://jarvis-championship-runner",
            "authorized_at": NOW,
            "expires_at": NOW + timedelta(hours=4),
            "production_write_allowed": False,
            "exploit_execution_allowed": False,
            "credential_capture_allowed": False,
            "ground_truth_access_allowed": False,
            "unrestricted_network_allowed": False,
        },
    )


def _run(competitor: CompetitorKind, *, bank=None, sandbox=None):
    bank = bank or _bank()
    sandbox = sandbox or _sandbox()
    return execution._seal_model(
        SystemExecutionReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "run_id": f"run-{competitor.value}-001",
            "competitor": competitor,
            "system_version": "verified-version-001",
            "task_set_fingerprint": bank.task_set_fingerprint,
            "environment_fingerprint": sandbox.environment_fingerprint,
            "evidence_class": CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
            "sandbox_fingerprint": sandbox.fingerprint,
            "started_at": NOW + timedelta(minutes=1),
            "completed_at": NOW + timedelta(minutes=31),
            "tasks_attempted": bank.task_count,
            "response_bundle_sha256": "5" * 64,
            "response_bundle_ref": f"sealed-output://{competitor.value}/run-001",
            "runner_attestation_refs": (f"attestation://runner/{competitor.value}",),
            "unsafe_offensive_content_events": 0,
            "unauthorized_action_events": 0,
            "production_mutation_events": 0,
            "ground_truth_accessed": False,
            "raw_credentials_persisted": False,
            "score_known_to_runner": False,
            "execution_authority_granted": False,
        },
    )


def _evaluator(run: SystemExecutionReceipt, bank: SealedTaskBankReceipt, *, one_failure: bool = True):
    results = []
    for track_index, track in enumerate(ChampionshipTrack):
        for sample in range(10):
            failed = one_failure and track_index == 0 and sample == 0
            results.append(
                EvaluatedTaskResult(
                    opaque_task_digest=f"{track_index * 10 + sample + 1:064x}",
                    track=track,
                    score=0.0 if failed else 1.0,
                    evaluator_reason_code="blind-evaluator-v1",
                    failure_class=FailureClass.DETECTION_MISS if failed else None,
                )
            )
    return execution._seal_model(
        BlindEvaluatorReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "evaluator_id": "independent-evaluator-001",
            "evaluator_version": "2026.08.22",
            "evaluator_key_id": bank.evaluator_key_id,
            "bank_fingerprint": bank.fingerprint,
            "run_fingerprint": run.fingerprint,
            "evaluated_at": NOW + timedelta(minutes=35),
            "results": tuple(results),
            "ground_truth_disclosed_to_runner": False,
            "signed_result_sha256": "6" * 64,
        },
    )


def _vendor_auth(competitor: CompetitorKind):
    values = {
        "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
        "competitor": competitor,
        "organization_ref": "organization://authorized-security-tenant",
        "identity_binding_refs": ("identity://competition-scoped",),
        "resource_binding_refs": ("resource://competition-workspace",),
        "authorization_evidence_ref": "evidence://owner/competition-approval",
        "authorized_at": NOW,
        "expires_at": NOW + timedelta(hours=4),
        "competition_use_authorized": True,
        "read_only_scope_verified": True,
        "credentials_embedded_in_receipt": False,
        "production_mutation_authority": False,
    }
    draft = CompetitorRunnerAuthorization.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return CompetitorRunnerAuthorization(
        **values,
        fingerprint=vendor._fingerprint(payload),
    )


def test_bank_rejects_repository_ground_truth():
    values = _bank().model_dump(mode="python", exclude={"fingerprint"})
    values["ground_truth_embedded_in_repository"] = True
    with pytest.raises(ValueError, match="seal_boundary"):
        execution._seal_model(SealedTaskBankReceipt, values)


def test_sandbox_rejects_production_write_and_ground_truth_access():
    values = _sandbox().model_dump(mode="python", exclude={"fingerprint"})
    values["production_write_allowed"] = True
    values["ground_truth_access_allowed"] = True
    with pytest.raises(ValueError, match="forbidden_authority"):
        execution._seal_model(ChampionshipSandboxAuthorization, values)


def test_blind_scoring_failure_classification_and_queue_do_not_leak_tasks():
    bank = _bank()
    sandbox = _sandbox()
    run = _run(CompetitorKind.JARVIS, bank=bank, sandbox=sandbox)
    evaluator = _evaluator(run, bank)

    score = blind_score_run(bank=bank, sandbox=sandbox, run=run, evaluator=evaluator)
    summary = classify_failures(run=run, evaluator=evaluator)
    queue = build_remediation_queue(bank=bank, summary=summary, created_at=NOW + timedelta(hours=1))

    assert score.blind_scoring_verified is True
    assert score.safety_floor_passed is True
    assert score.overall_score < 1.0
    assert len(summary.aggregates) == 1
    assert summary.aggregates[0].failure_class is FailureClass.DETECTION_MISS
    assert queue.source_task_ids_included is False
    assert queue.source_ground_truth_included is False
    assert queue.automatic_model_promotion_allowed is False
    assert all(item.fresh_championship_rotation_required for item in queue.items)
    assert all(not item.sealed_task_content_allowed for item in queue.items)


def test_retest_rejects_same_bank_and_accepts_fresh_rotation():
    first = _bank()
    run = _run(CompetitorKind.JARVIS, bank=first)
    summary = classify_failures(run=run, evaluator=_evaluator(run, first))
    queue = build_remediation_queue(bank=first, summary=summary, created_at=NOW + timedelta(hours=1))

    with pytest.raises(ValueError, match="fresh_rotation"):
        authorize_retest_rotation(previous_bank=first, next_bank=first, queue=queue)

    second = _bank(rotation="rotation-002", task_hash="7" * 64, truth_hash="8" * 64)
    authorize_retest_rotation(previous_bank=first, next_bank=second, queue=queue)


def test_cycle_fail_closed_until_every_real_baseline_exists():
    bank = _bank()
    sandbox = _sandbox()
    jarvis = _run(CompetitorKind.JARVIS, bank=bank, sandbox=sandbox)

    receipt = assess_cycle(bank=bank, sandbox=sandbox, runs=(jarvis,))

    assert receipt.status is ChampionshipCycleStatus.WAITING_EXTERNAL_BASELINES
    assert receipt.verified_leader_claim_allowed is False
    assert receipt.production_security_superiority_claim_allowed is False
    assert "championship_all_real_common_harness_runs_not_complete" in receipt.blockers


def test_vendor_adapter_requires_real_organization_authority():
    spec = default_competitor_adapter_specs()[0]
    status, blockers = assess_runner_authority(adapter=spec, authorization=None, now=NOW)

    assert status is RunnerAuthorityStatus.MISSING_ORGANIZATION_ACCESS
    assert blockers == ("competitor_organization_authorization_receipt_missing",)


class _ReceiptRunner:
    def __init__(self, receipt: SystemExecutionReceipt):
        self.receipt = receipt

    def run_common_harness(self, **_kwargs):
        return self.receipt


def test_vendor_run_port_accepts_only_bound_real_receipt():
    bank = _bank()
    sandbox = _sandbox()
    spec = default_competitor_adapter_specs()[0]
    authorization = _vendor_auth(spec.competitor)
    receipt = _run(spec.competitor, bank=bank, sandbox=sandbox)

    observed = execute_real_competitor_run(
        adapter=spec,
        authorization=authorization,
        bank=bank,
        sandbox=sandbox,
        runner=_ReceiptRunner(receipt),
        now=NOW + timedelta(minutes=1),
    )

    assert observed.competitor is spec.competitor
    assert observed.tasks_attempted == bank.task_count


def test_evaluator_cannot_disclose_ground_truth():
    bank = _bank()
    run = _run(CompetitorKind.JARVIS, bank=bank)
    values = _evaluator(run, bank).model_dump(mode="python", exclude={"fingerprint"})
    values["ground_truth_disclosed_to_runner"] = True
    with pytest.raises(ValueError, match="ground_truth_leak"):
        execution._seal_model(BlindEvaluatorReceipt, values)
