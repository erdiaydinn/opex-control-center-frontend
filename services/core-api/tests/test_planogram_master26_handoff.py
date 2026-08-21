from __future__ import annotations

from uuid import UUID

import pytest

from app.core.security import Principal
from app.modules.planogram import execution_service
from app.modules.planogram.execution import PlanogramExecutionError

TENANT = UUID("11111111-1111-4111-8111-111111111111")
ASSIGNMENT = UUID("22222222-2222-4222-8222-222222222222")
PLAN = UUID("33333333-3333-4333-8333-333333333333")
PROMOTION = UUID("44444444-4444-4444-8444-444444444444")


def principal() -> Principal:
    return Principal(
        subject="planogram-consumer",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=("action:planogram:acceptFieldEvidence",),
        auth_mode="development",
    )


def assignment() -> dict[str, object]:
    return {
        "assignment_id": ASSIGNMENT,
        "plan_version_id": PLAN,
        "store_code": "FULYA",
        "assignment_status": "acknowledged",
        "plan_status": "approved",
        "physical_truth_attested": True,
        "plan_payload": {
            "aisles": [
                {
                    "aisle_id": "A01",
                    "modules": [
                        {
                            "module_id": "M01",
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "products": [{"sku": "SKU-1", "facing_count": 2}],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "plan_fingerprint": "a" * 64,
    }


def context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": PROMOTION,
        "consumer_module": "planogram",
        "adapter_key": "planogram.compliance_observation.v1",
        "field_decision": "approve",
        "location_id": "FULYA",
        "candidate_fingerprint": "b" * 64,
        "proposal_fingerprint": "c" * 64,
        "decision_fingerprint": "d" * 64,
        "requested_by": "field-reviewer",
        "consumer_receipt_id": None,
        "candidate_payload": {
            "plan_version_id": str(PLAN),
            "sku": "SKU-1",
            "actual_aisle_id": "A01",
            "actual_module_id": "M01",
            "actual_shelf_no": "1",
            "actual_facing_count": 2,
        },
    }
    base.update(overrides)
    return base


async def _install_common(monkeypatch, *, promotion_context=None):
    async def fake_assignment(*args, **kwargs):
        return assignment()

    async def fake_context(*args, **kwargs):
        return promotion_context or context()

    monkeypatch.setattr(execution_service, "get_assignment_plan", fake_assignment)
    monkeypatch.setattr(execution_service, "get_promotion_context_in_session", fake_context)


@pytest.mark.asyncio
async def test_handoff_rejects_wrong_adapter(monkeypatch) -> None:
    await _install_common(
        monkeypatch,
        promotion_context=context(adapter_key="planogram.fixture_measurement.v1"),
    )
    with pytest.raises(
        PlanogramExecutionError,
        match="promotion_adapter_must_be_planogram_compliance_v1",
    ):
        await execution_service.consume_compliance_promotion(
            object(),
            principal(),
            assignment_id=ASSIGNMENT,
            field_promotion_id=PROMOTION,
        )


@pytest.mark.asyncio
async def test_handoff_rejects_wrong_store(monkeypatch) -> None:
    await _install_common(monkeypatch, promotion_context=context(location_id="OTHER"))
    with pytest.raises(
        PlanogramExecutionError,
        match="promotion_location_does_not_match_assignment_store",
    ):
        await execution_service.consume_compliance_promotion(
            object(),
            principal(),
            assignment_id=ASSIGNMENT,
            field_promotion_id=PROMOTION,
        )


@pytest.mark.asyncio
async def test_handoff_rejects_wrong_exact_plan_version(monkeypatch) -> None:
    candidate = dict(context()["candidate_payload"])
    candidate["plan_version_id"] = "55555555-5555-4555-8555-555555555555"
    await _install_common(
        monkeypatch,
        promotion_context=context(candidate_payload=candidate),
    )
    with pytest.raises(
        PlanogramExecutionError,
        match="promotion_plan_version_does_not_match_assignment",
    ):
        await execution_service.consume_compliance_promotion(
            object(),
            principal(),
            assignment_id=ASSIGNMENT,
            field_promotion_id=PROMOTION,
        )


@pytest.mark.asyncio
async def test_valid_handoff_records_observation_and_receipt_in_same_session(monkeypatch) -> None:
    session = object()
    await _install_common(monkeypatch)
    seen: dict[str, object] = {}

    async def fake_insert(received_session, *args, **kwargs):
        assert received_session is session
        seen["observation"] = kwargs
        return {
            "id": UUID("66666666-6666-4666-8666-666666666666"),
            "idempotent_replay": False,
        }

    async def fake_receipt(received_session, *args, **kwargs):
        assert received_session is session
        seen["receipt"] = kwargs
        return {"id": "receipt-1", "decision": "accept"}

    monkeypatch.setattr(execution_service, "insert_compliance_observation", fake_insert)
    monkeypatch.setattr(
        execution_service,
        "record_consumer_receipt_in_session",
        fake_receipt,
    )

    result = await execution_service.consume_compliance_promotion(
        session,
        principal(),
        assignment_id=ASSIGNMENT,
        field_promotion_id=PROMOTION,
    )

    assert result["idempotent_replay"] is False
    assert seen["observation"]["assignment_id"] == ASSIGNMENT
    assert seen["observation"]["plan_version_id"] == PLAN
    assert seen["observation"]["evaluation"]["result"] == "compliant"
    assert seen["receipt"]["consumer_module"] == "planogram"
    assert str(seen["receipt"]["destination_candidate_ref"]).startswith(
        "planogram-compliance:"
    )
    assert result["truth_boundary"] == {
        "field_evidence_is_planogram_truth": False,
        "approved_plan_is_execution_baseline": True,
        "compliance_observation_is_append_only": True,
    }
