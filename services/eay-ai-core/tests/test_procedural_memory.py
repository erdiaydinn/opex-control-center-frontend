from datetime import datetime, timezone

from app.procedural_memory import (
    ProcedureDemonstration,
    ProcedureStatus,
    ProcedureStep,
    ProcedureStepKind,
    compile_procedure,
    procedure_step_fingerprint,
    revalidate_environment,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 2, 30, tzinfo=UTC)
ENV = "a" * 64


def _steps():
    return (
        ProcedureStep(
            step_id="read",
            kind=ProcedureStepKind.API,
            operation_ref="capability://inventory.read-stock",
        ),
        ProcedureStep(
            step_id="write",
            kind=ProcedureStepKind.API,
            operation_ref="candidate://inventory.adjust-stock",
            side_effect=True,
            expected_effect_ref="stock://decrement",
            verifier_ref="capability://inventory.read-stock",
        ),
        ProcedureStep(
            step_id="verify",
            kind=ProcedureStepKind.READBACK,
            operation_ref="capability://inventory.read-stock",
        ),
    )


def _demo(demo_id, **overrides):
    payload = dict(
        demonstration_id=demo_id,
        tenant_id="warehouse:fulya",
        capability_name="inventory.adjust-stock",
        observed_at=NOW,
        step_fingerprint=procedure_step_fingerprint(_steps()),
        successful=True,
        effect_verified=True,
        ambiguous_outcome=False,
        environment_fingerprint=ENV,
        evidence_refs=(f"evidence://{demo_id}",),
    )
    payload.update(overrides)
    return ProcedureDemonstration(**payload)


def test_repeated_verified_write_demonstrations_compile_to_validated_capability():
    capability = compile_procedure(
        tenant_id="warehouse:fulya",
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[_demo("one"), _demo("two")],
    )

    assert capability.status is ProcedureStatus.VALIDATED
    assert capability.direct_execution_allowed is True
    assert capability.requires_revalidation is False
    assert capability.demonstrations == ("one", "two")


def test_single_write_demo_is_not_enough_for_direct_execution():
    capability = compile_procedure(
        tenant_id="warehouse:fulya",
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[_demo("one")],
    )

    assert capability.status is ProcedureStatus.CANDIDATE
    assert capability.direct_execution_allowed is False
    assert "procedure_verified_demonstrations_insufficient" in capability.blockers
    assert "procedure_write_requires_repeated_effect_verification" in capability.blockers


def test_ambiguous_demo_blocks_compilation_even_if_other_runs_succeeded():
    capability = compile_procedure(
        tenant_id="warehouse:fulya",
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[
            _demo("one"),
            _demo("two"),
            _demo("ambiguous", successful=False, effect_verified=False, ambiguous_outcome=True),
        ],
    )

    assert capability.direct_execution_allowed is False
    assert "procedure_contains_ambiguous_demonstration" in capability.blockers


def test_environment_drift_suspends_previously_validated_procedure():
    capability = compile_procedure(
        tenant_id="warehouse:fulya",
        capability_name="inventory.adjust-stock",
        steps=_steps(),
        demonstrations=[_demo("one"), _demo("two")],
    )
    suspended = revalidate_environment(
        capability,
        observed_environment_fingerprint="b" * 64,
    )

    assert suspended.status is ProcedureStatus.SUSPENDED
    assert suspended.direct_execution_allowed is False
    assert suspended.requires_revalidation is True
    assert "procedure_runtime_environment_drift" in suspended.blockers
