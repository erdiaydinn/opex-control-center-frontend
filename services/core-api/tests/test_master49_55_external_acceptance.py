from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from app.acceptance.external_evidence import (
    EvidenceRecord,
    build_external_item_refs,
    evaluate_requirement,
    load_requirements,
)

ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS = ROOT / "docs/governance/eay_external_acceptance_requirements.json"
TENANT = "tenant-a"
RELEASE = "eay-rc-2026-08-18"
CANDIDATE = "a" * 40
NOW = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)


def _record(
    requirement: dict[str, object],
    key: str,
    *,
    evidence_class: str = "REAL_ENVIRONMENT",
    status: str = "PASS",
    release_id: str = RELEASE,
    candidate_sha: str = CANDIDATE,
    observed_at: datetime | None = None,
    expires_at: datetime | None = None,
    provenance: str | None = None,
) -> EvidenceRecord:
    observed = observed_at or NOW - timedelta(hours=2)
    expires = expires_at or NOW + timedelta(days=7)
    return EvidenceRecord(
        tenant_id=TENANT,
        release_id=release_id,
        candidate_sha=candidate_sha,
        requirement_key=str(requirement["key"]),
        evidence_key=key,
        evidence_class=evidence_class,
        status=status,
        environment="corp-prod-readonly",
        provenance=provenance if provenance is not None else f"evidence:{key}",
        artifact_sha256=sha256(key.encode()).hexdigest(),
        approver="security-owner",
        observed_at=observed,
        expires_at=expires,
    )


def _records(
    requirement: dict[str, object],
    *,
    evidence_class: str = "REAL_ENVIRONMENT",
) -> tuple[EvidenceRecord, ...]:
    return tuple(
        _record(requirement, str(key), evidence_class=evidence_class)
        for key in requirement["evidence"]
    )


def _evaluate(
    requirement: dict[str, object], records: tuple[EvidenceRecord, ...]
) -> tuple[bool, tuple[str, ...]]:
    return evaluate_requirement(
        requirement,
        records,
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW,
    )


def test_repository_or_synthetic_evidence_cannot_satisfy_external_gates() -> None:
    requirement = load_requirements(REQUIREMENTS)["requirements"][0]
    for evidence_class in ("REPOSITORY", "SYNTHETIC"):
        ok, blockers = _evaluate(
            requirement,
            _records(requirement, evidence_class=evidence_class),
        )
        assert not ok
        assert blockers
        assert all("wrong_evidence_class" in blocker for blocker in blockers)


def test_real_identity_requires_every_proof_with_complete_provenance() -> None:
    requirement = load_requirements(REQUIREMENTS)["requirements"][0]
    records = _records(requirement)
    assert _evaluate(requirement, records) == (True, ())

    incomplete = list(records)
    incomplete[0] = replace(incomplete[0], provenance="")
    ok, blockers = _evaluate(requirement, tuple(incomplete))
    assert not ok
    assert f"{incomplete[0].evidence_key}:incomplete_provenance" in blockers


def test_newer_revocation_wins_over_older_pass_regardless_of_tuple_order() -> None:
    requirement = load_requirements(REQUIREMENTS)["requirements"][0]
    records = list(_records(requirement))
    key = records[0].evidence_key
    old_pass = replace(records[0], observed_at=NOW - timedelta(hours=3))
    newer_revocation = replace(
        records[0],
        status="REVOKED",
        observed_at=NOW - timedelta(hours=1),
        artifact_sha256="b" * 64,
    )
    records[0] = newer_revocation
    records.append(old_pass)

    ok, blockers = _evaluate(requirement, tuple(records))
    assert not ok
    assert f"{key}:revoked" in blockers


def test_expired_or_other_release_evidence_cannot_be_reused() -> None:
    requirement = load_requirements(REQUIREMENTS)["requirements"][0]
    expired = list(_records(requirement))
    expired[0] = replace(
        expired[0],
        observed_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(hours=1),
    )
    ok, blockers = _evaluate(requirement, tuple(expired))
    assert not ok
    assert f"{expired[0].evidence_key}:expired" in blockers

    prior_release = tuple(
        replace(record, release_id="old-release")
        for record in _records(requirement)
    )
    ok, blockers = _evaluate(requirement, prior_release)
    assert not ok
    assert all(blocker.endswith(":missing") for blocker in blockers)


def test_passing_item_refs_are_deterministic_release_bound_ledger_fingerprints() -> None:
    requirements = load_requirements(REQUIREMENTS)
    requirement = requirements["requirements"][0]
    records = _records(requirement)
    refs = build_external_item_refs(
        requirements,
        records,
        tenant_id=TENANT,
        release_id=RELEASE,
        candidate_sha=CANDIDATE,
        as_of=NOW,
    )
    assert refs[49].startswith("ledger-sha256:")
    assert len(refs[49]) == len("ledger-sha256:") + 64
    assert set(refs) == {49}
