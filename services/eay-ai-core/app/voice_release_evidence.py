from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .voice_release_gate import VoiceLanguageEval, VoiceReleaseDecision, evaluate_voice_release
from .voice_runtime import CORE_LANGUAGES


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


def _require_sha(value: str, code: str) -> str:
    value = str(value)
    if not _valid_sha256(value):
        raise ValueError(code)
    return value


def _utc_iso(value: datetime | None) -> str:
    when = value or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).isoformat()


def _eval_payload(evaluation: VoiceLanguageEval) -> dict[str, object]:
    sealed = evaluation.sealed()
    return {
        "language": sealed.language,
        "sample_count": sealed.sample_count,
        "stt_word_error_rate": sealed.stt_word_error_rate,
        "semantic_consistency_rate": sealed.semantic_consistency_rate,
        "human_naturalness_score": sealed.human_naturalness_score,
        "citation_readback_accuracy": sealed.citation_readback_accuracy,
        "p95_first_audio_ms": sealed.p95_first_audio_ms,
        "p95_barge_in_ms": sealed.p95_barge_in_ms,
        "interruption_success_rate": sealed.interruption_success_rate,
        "p95_cancel_propagation_ms": sealed.p95_cancel_propagation_ms,
        "approval_replay_accept_count": sealed.approval_replay_accept_count,
        "fingerprint": sealed.fingerprint,
    }


def _eval_from_payload(payload: dict[str, object]) -> VoiceLanguageEval:
    evaluation = VoiceLanguageEval(
        language=str(payload["language"]),
        sample_count=int(payload["sample_count"]),
        stt_word_error_rate=float(payload["stt_word_error_rate"]),
        semantic_consistency_rate=float(payload["semantic_consistency_rate"]),
        human_naturalness_score=float(payload["human_naturalness_score"]),
        citation_readback_accuracy=float(payload["citation_readback_accuracy"]),
        p95_first_audio_ms=int(payload["p95_first_audio_ms"]),
        p95_barge_in_ms=int(payload["p95_barge_in_ms"]),
        interruption_success_rate=float(payload["interruption_success_rate"]),
        p95_cancel_propagation_ms=int(payload["p95_cancel_propagation_ms"]),
        approval_replay_accept_count=int(payload["approval_replay_accept_count"]),
        fingerprint=str(payload["fingerprint"]),
    )
    resealed = evaluation.sealed()
    if resealed.fingerprint != evaluation.fingerprint:
        raise ValueError("voice_release_evidence_metric_fingerprint_drift")
    return evaluation


@dataclass(frozen=True)
class VoiceLanguageMeasurementEvidence:
    language: str
    evaluation: VoiceLanguageEval
    deployment_manifest_fingerprint: str
    model_execution_identity_fingerprint: str
    tts_bundle_execution_identity_fingerprint: str
    runtime_attestation_bundle_fingerprint: str
    eval_suite_sha256: str
    measurement_harness_sha256: str
    runtime_environment_fingerprint: str
    raw_measurement_manifest_sha256: str
    human_review_manifest_sha256: str
    reviewer: str
    approval_reference: str
    measured_at: str
    fingerprint: str

    def payload(self) -> dict[str, object]:
        return {
            "language": self.language,
            "evaluation": _eval_payload(self.evaluation),
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "model_execution_identity_fingerprint": self.model_execution_identity_fingerprint,
            "tts_bundle_execution_identity_fingerprint": self.tts_bundle_execution_identity_fingerprint,
            "runtime_attestation_bundle_fingerprint": self.runtime_attestation_bundle_fingerprint,
            "eval_suite_sha256": self.eval_suite_sha256,
            "measurement_harness_sha256": self.measurement_harness_sha256,
            "runtime_environment_fingerprint": self.runtime_environment_fingerprint,
            "raw_measurement_manifest_sha256": self.raw_measurement_manifest_sha256,
            "human_review_manifest_sha256": self.human_review_manifest_sha256,
            "reviewer": self.reviewer,
            "approval_reference": self.approval_reference,
            "measured_at": self.measured_at,
        }

    def validate(self) -> None:
        if self.language not in CORE_LANGUAGES or self.evaluation.language != self.language:
            raise ValueError("voice_release_evidence_language_mismatch")
        self.evaluation.validate()
        for value, code in (
            (self.deployment_manifest_fingerprint, "voice_release_evidence_deployment_manifest_invalid"),
            (self.model_execution_identity_fingerprint, "voice_release_evidence_model_identity_invalid"),
            (self.tts_bundle_execution_identity_fingerprint, "voice_release_evidence_tts_bundle_invalid"),
            (self.runtime_attestation_bundle_fingerprint, "voice_release_evidence_runtime_attestation_invalid"),
            (self.eval_suite_sha256, "voice_release_evidence_eval_suite_invalid"),
            (self.measurement_harness_sha256, "voice_release_evidence_harness_invalid"),
            (self.runtime_environment_fingerprint, "voice_release_evidence_environment_invalid"),
            (self.raw_measurement_manifest_sha256, "voice_release_evidence_raw_manifest_invalid"),
            (self.human_review_manifest_sha256, "voice_release_evidence_human_review_invalid"),
            (self.fingerprint, "voice_release_evidence_fingerprint_invalid"),
        ):
            _require_sha(value, code)
        if len(self.reviewer.strip()) < 2:
            raise ValueError("voice_release_evidence_reviewer_required")
        if len(self.approval_reference.strip()) < 3:
            raise ValueError("voice_release_evidence_approval_reference_required")
        try:
            measured = datetime.fromisoformat(self.measured_at)
        except ValueError as exc:
            raise ValueError("voice_release_evidence_measured_at_invalid") from exc
        if measured.tzinfo is None:
            raise ValueError("voice_release_evidence_measured_at_timezone_required")
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("voice_release_evidence_fingerprint_drift")


def seal_voice_language_measurement_evidence(
    *,
    evaluation: VoiceLanguageEval,
    deployment_manifest_fingerprint: str,
    model_execution_identity_fingerprint: str,
    tts_bundle_execution_identity_fingerprint: str,
    runtime_attestation_bundle_fingerprint: str,
    eval_suite_sha256: str,
    measurement_harness_sha256: str,
    runtime_environment_fingerprint: str,
    raw_measurement_manifest_sha256: str,
    human_review_manifest_sha256: str,
    reviewer: str,
    approval_reference: str,
    measured_at: datetime | None = None,
) -> VoiceLanguageMeasurementEvidence:
    sealed_eval = evaluation.sealed()
    language = sealed_eval.language.strip().lower()
    if language not in CORE_LANGUAGES:
        raise ValueError("voice_release_evidence_language_not_enabled")
    reviewer = reviewer.strip()
    approval_reference = approval_reference.strip()
    payload = {
        "language": language,
        "evaluation": _eval_payload(sealed_eval),
        "deployment_manifest_fingerprint": _require_sha(deployment_manifest_fingerprint, "voice_release_evidence_deployment_manifest_invalid"),
        "model_execution_identity_fingerprint": _require_sha(model_execution_identity_fingerprint, "voice_release_evidence_model_identity_invalid"),
        "tts_bundle_execution_identity_fingerprint": _require_sha(tts_bundle_execution_identity_fingerprint, "voice_release_evidence_tts_bundle_invalid"),
        "runtime_attestation_bundle_fingerprint": _require_sha(runtime_attestation_bundle_fingerprint, "voice_release_evidence_runtime_attestation_invalid"),
        "eval_suite_sha256": _require_sha(eval_suite_sha256, "voice_release_evidence_eval_suite_invalid"),
        "measurement_harness_sha256": _require_sha(measurement_harness_sha256, "voice_release_evidence_harness_invalid"),
        "runtime_environment_fingerprint": _require_sha(runtime_environment_fingerprint, "voice_release_evidence_environment_invalid"),
        "raw_measurement_manifest_sha256": _require_sha(raw_measurement_manifest_sha256, "voice_release_evidence_raw_manifest_invalid"),
        "human_review_manifest_sha256": _require_sha(human_review_manifest_sha256, "voice_release_evidence_human_review_invalid"),
        "reviewer": reviewer,
        "approval_reference": approval_reference,
        "measured_at": _utc_iso(measured_at),
    }
    evidence = VoiceLanguageMeasurementEvidence(
        language=language,
        evaluation=sealed_eval,
        deployment_manifest_fingerprint=str(payload["deployment_manifest_fingerprint"]),
        model_execution_identity_fingerprint=str(payload["model_execution_identity_fingerprint"]),
        tts_bundle_execution_identity_fingerprint=str(payload["tts_bundle_execution_identity_fingerprint"]),
        runtime_attestation_bundle_fingerprint=str(payload["runtime_attestation_bundle_fingerprint"]),
        eval_suite_sha256=str(payload["eval_suite_sha256"]),
        measurement_harness_sha256=str(payload["measurement_harness_sha256"]),
        runtime_environment_fingerprint=str(payload["runtime_environment_fingerprint"]),
        raw_measurement_manifest_sha256=str(payload["raw_measurement_manifest_sha256"]),
        human_review_manifest_sha256=str(payload["human_review_manifest_sha256"]),
        reviewer=reviewer,
        approval_reference=approval_reference,
        measured_at=str(payload["measured_at"]),
        fingerprint=_sha256(payload),
    )
    evidence.validate()
    return evidence


@dataclass(frozen=True)
class GovernedVoiceReleaseDecision:
    approved: bool
    violations: tuple[str, ...]
    deployment_manifest_fingerprint: str
    model_execution_identity_fingerprint: str
    tts_bundle_execution_identity_fingerprint: str
    runtime_attestation_bundle_fingerprint: str
    eval_suite_sha256: str
    measurement_harness_sha256: str
    language_evidence_fingerprints: tuple[str, ...]
    metric_decision_fingerprint: str
    reviewer: str
    approval_reference: str
    decided_at: str
    fingerprint: str

    def payload(self) -> dict[str, object]:
        return {
            "approved": self.approved,
            "violations": self.violations,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "model_execution_identity_fingerprint": self.model_execution_identity_fingerprint,
            "tts_bundle_execution_identity_fingerprint": self.tts_bundle_execution_identity_fingerprint,
            "runtime_attestation_bundle_fingerprint": self.runtime_attestation_bundle_fingerprint,
            "eval_suite_sha256": self.eval_suite_sha256,
            "measurement_harness_sha256": self.measurement_harness_sha256,
            "language_evidence_fingerprints": self.language_evidence_fingerprints,
            "metric_decision_fingerprint": self.metric_decision_fingerprint,
            "reviewer": self.reviewer,
            "approval_reference": self.approval_reference,
            "decided_at": self.decided_at,
        }

    def validate(self) -> None:
        for value, code in (
            (self.deployment_manifest_fingerprint, "voice_release_decision_deployment_manifest_invalid"),
            (self.model_execution_identity_fingerprint, "voice_release_decision_model_identity_invalid"),
            (self.tts_bundle_execution_identity_fingerprint, "voice_release_decision_tts_bundle_invalid"),
            (self.runtime_attestation_bundle_fingerprint, "voice_release_decision_runtime_attestation_invalid"),
            (self.eval_suite_sha256, "voice_release_decision_eval_suite_invalid"),
            (self.measurement_harness_sha256, "voice_release_decision_harness_invalid"),
            (self.metric_decision_fingerprint, "voice_release_decision_metric_fingerprint_invalid"),
            (self.fingerprint, "voice_release_decision_fingerprint_invalid"),
        ):
            _require_sha(value, code)
        if len(self.language_evidence_fingerprints) != len(CORE_LANGUAGES):
            raise ValueError("voice_release_decision_language_evidence_count_invalid")
        if len(set(self.language_evidence_fingerprints)) != len(self.language_evidence_fingerprints):
            raise ValueError("voice_release_decision_duplicate_evidence")
        for value in self.language_evidence_fingerprints:
            _require_sha(value, "voice_release_decision_language_evidence_invalid")
        if len(self.reviewer.strip()) < 2 or len(self.approval_reference.strip()) < 3:
            raise ValueError("voice_release_decision_human_approval_required")
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("voice_release_decision_fingerprint_drift")


class VoiceReleaseEvidenceRegistry:
    """Immutable, human-reviewed measurement and release evidence for voice rollout.

    The registry stores hashes/metrics only. Raw microphone audio, generated PCM,
    transcripts and review text remain outside this database and are referenced by
    immutable manifest hashes.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS voice_language_measurement_evidence (
                fingerprint TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                deployment_manifest_fingerprint TEXT NOT NULL,
                payload_json TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS voice_governed_release_decisions (
                fingerprint TEXT PRIMARY KEY,
                approved INTEGER NOT NULL,
                deployment_manifest_fingerprint TEXT NOT NULL,
                payload_json TEXT NOT NULL
                )"""
            )

    def record_language(self, evidence: VoiceLanguageMeasurementEvidence) -> VoiceLanguageMeasurementEvidence:
        evidence.validate()
        payload_json = json.dumps(evidence.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO voice_language_measurement_evidence(fingerprint,language,deployment_manifest_fingerprint,payload_json) VALUES (?,?,?,?)",
                    (evidence.fingerprint, evidence.language, evidence.deployment_manifest_fingerprint, payload_json),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("voice_release_evidence_already_recorded") from exc
        return self.require_language(evidence.fingerprint)

    def require_language(self, fingerprint: str) -> VoiceLanguageMeasurementEvidence:
        _require_sha(fingerprint, "voice_release_evidence_lookup_fingerprint_invalid")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload_json FROM voice_language_measurement_evidence WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
        if row is None:
            raise KeyError("voice_release_evidence_not_found")
        payload = json.loads(row[0])
        evaluation = _eval_from_payload(payload["evaluation"])
        evidence = VoiceLanguageMeasurementEvidence(
            language=payload["language"],
            evaluation=evaluation,
            deployment_manifest_fingerprint=payload["deployment_manifest_fingerprint"],
            model_execution_identity_fingerprint=payload["model_execution_identity_fingerprint"],
            tts_bundle_execution_identity_fingerprint=payload["tts_bundle_execution_identity_fingerprint"],
            runtime_attestation_bundle_fingerprint=payload["runtime_attestation_bundle_fingerprint"],
            eval_suite_sha256=payload["eval_suite_sha256"],
            measurement_harness_sha256=payload["measurement_harness_sha256"],
            runtime_environment_fingerprint=payload["runtime_environment_fingerprint"],
            raw_measurement_manifest_sha256=payload["raw_measurement_manifest_sha256"],
            human_review_manifest_sha256=payload["human_review_manifest_sha256"],
            reviewer=payload["reviewer"],
            approval_reference=payload["approval_reference"],
            measured_at=payload["measured_at"],
            fingerprint=fingerprint,
        )
        evidence.validate()
        return evidence

    @staticmethod
    def _require_same(evidence: tuple[VoiceLanguageMeasurementEvidence, ...], field: str, code: str) -> str:
        values = {str(getattr(item, field)) for item in evidence}
        if len(values) != 1:
            raise ValueError(code)
        return next(iter(values))

    def record_release(
        self,
        *,
        language_evidence_fingerprints: Iterable[str],
        reviewer: str,
        approval_reference: str,
        decided_at: datetime | None = None,
    ) -> GovernedVoiceReleaseDecision:
        requested = tuple(language_evidence_fingerprints)
        if len(requested) != len(CORE_LANGUAGES) or len(set(requested)) != len(requested):
            raise ValueError("voice_release_decision_exact_core_evidence_required")
        evidence = tuple(self.require_language(item) for item in requested)
        by_language = {item.language: item for item in evidence}
        if set(by_language) != set(CORE_LANGUAGES) or len(by_language) != len(evidence):
            raise ValueError("voice_release_decision_exact_core_languages_required")

        deployment_fp = self._require_same(evidence, "deployment_manifest_fingerprint", "voice_release_decision_deployment_drift")
        model_fp = self._require_same(evidence, "model_execution_identity_fingerprint", "voice_release_decision_model_drift")
        tts_bundle_fp = self._require_same(evidence, "tts_bundle_execution_identity_fingerprint", "voice_release_decision_tts_bundle_drift")
        runtime_attestation_fp = self._require_same(evidence, "runtime_attestation_bundle_fingerprint", "voice_release_decision_runtime_attestation_drift")
        eval_suite_sha = self._require_same(evidence, "eval_suite_sha256", "voice_release_decision_eval_suite_drift")
        harness_sha = self._require_same(evidence, "measurement_harness_sha256", "voice_release_decision_harness_drift")
        metric_decision: VoiceReleaseDecision = evaluate_voice_release(item.evaluation for item in evidence)

        reviewer = reviewer.strip()
        approval_reference = approval_reference.strip()
        if len(reviewer) < 2 or len(approval_reference) < 3:
            raise ValueError("voice_release_decision_human_approval_required")
        ordered_evidence = tuple(by_language[language].fingerprint for language in CORE_LANGUAGES)
        payload = {
            "approved": metric_decision.approved,
            "violations": metric_decision.violations,
            "deployment_manifest_fingerprint": deployment_fp,
            "model_execution_identity_fingerprint": model_fp,
            "tts_bundle_execution_identity_fingerprint": tts_bundle_fp,
            "runtime_attestation_bundle_fingerprint": runtime_attestation_fp,
            "eval_suite_sha256": eval_suite_sha,
            "measurement_harness_sha256": harness_sha,
            "language_evidence_fingerprints": ordered_evidence,
            "metric_decision_fingerprint": metric_decision.fingerprint,
            "reviewer": reviewer,
            "approval_reference": approval_reference,
            "decided_at": _utc_iso(decided_at),
        }
        decision = GovernedVoiceReleaseDecision(
            approved=metric_decision.approved,
            violations=metric_decision.violations,
            deployment_manifest_fingerprint=deployment_fp,
            model_execution_identity_fingerprint=model_fp,
            tts_bundle_execution_identity_fingerprint=tts_bundle_fp,
            runtime_attestation_bundle_fingerprint=runtime_attestation_fp,
            eval_suite_sha256=eval_suite_sha,
            measurement_harness_sha256=harness_sha,
            language_evidence_fingerprints=ordered_evidence,
            metric_decision_fingerprint=metric_decision.fingerprint,
            reviewer=reviewer,
            approval_reference=approval_reference,
            decided_at=str(payload["decided_at"]),
            fingerprint=_sha256(payload),
        )
        decision.validate()
        payload_json = json.dumps(decision.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO voice_governed_release_decisions(fingerprint,approved,deployment_manifest_fingerprint,payload_json) VALUES (?,?,?,?)",
                    (decision.fingerprint, 1 if decision.approved else 0, decision.deployment_manifest_fingerprint, payload_json),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("voice_release_decision_already_recorded") from exc
        return self.require_release(decision.fingerprint, require_approved=False)

    def require_release(
        self,
        fingerprint: str,
        *,
        require_approved: bool = True,
        deployment_manifest_fingerprint: str | None = None,
        model_execution_identity_fingerprint: str | None = None,
        tts_bundle_execution_identity_fingerprint: str | None = None,
        runtime_attestation_bundle_fingerprint: str | None = None,
    ) -> GovernedVoiceReleaseDecision:
        _require_sha(fingerprint, "voice_release_decision_lookup_fingerprint_invalid")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload_json FROM voice_governed_release_decisions WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
        if row is None:
            raise KeyError("voice_release_decision_not_found")
        payload = json.loads(row[0])
        decision = GovernedVoiceReleaseDecision(
            approved=bool(payload["approved"]),
            violations=tuple(payload["violations"]),
            deployment_manifest_fingerprint=payload["deployment_manifest_fingerprint"],
            model_execution_identity_fingerprint=payload["model_execution_identity_fingerprint"],
            tts_bundle_execution_identity_fingerprint=payload["tts_bundle_execution_identity_fingerprint"],
            runtime_attestation_bundle_fingerprint=payload["runtime_attestation_bundle_fingerprint"],
            eval_suite_sha256=payload["eval_suite_sha256"],
            measurement_harness_sha256=payload["measurement_harness_sha256"],
            language_evidence_fingerprints=tuple(payload["language_evidence_fingerprints"]),
            metric_decision_fingerprint=payload["metric_decision_fingerprint"],
            reviewer=payload["reviewer"],
            approval_reference=payload["approval_reference"],
            decided_at=payload["decided_at"],
            fingerprint=fingerprint,
        )
        decision.validate()
        if require_approved and not decision.approved:
            raise ValueError("voice_release_decision_not_approved")
        for expected, actual, code in (
            (deployment_manifest_fingerprint, decision.deployment_manifest_fingerprint, "voice_release_decision_deployment_mismatch"),
            (model_execution_identity_fingerprint, decision.model_execution_identity_fingerprint, "voice_release_decision_model_mismatch"),
            (tts_bundle_execution_identity_fingerprint, decision.tts_bundle_execution_identity_fingerprint, "voice_release_decision_tts_bundle_mismatch"),
            (runtime_attestation_bundle_fingerprint, decision.runtime_attestation_bundle_fingerprint, "voice_release_decision_runtime_attestation_mismatch"),
        ):
            if expected is not None and expected != actual:
                raise ValueError(code)
        return decision
