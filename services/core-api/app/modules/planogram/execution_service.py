from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.field_intelligence.promotion import FieldPromotionError
from app.modules.field_intelligence.promotion_consumer_session import (
    get_promotion_context_in_session,
    record_consumer_receipt_in_session,
)
from app.modules.planogram.execution import PlanogramExecutionError, evaluate_compliance
from app.modules.planogram.repository_execution import (
    get_assignment_plan,
    insert_compliance_observation,
)

COMPLIANCE_ADAPTER = "planogram.compliance_observation.v1"


async def consume_compliance_promotion(
    session: AsyncSession,
    principal: Principal,
    *,
    assignment_id: UUID,
    field_promotion_id: UUID,
) -> dict[str, Any]:
    assignment = await get_assignment_plan(session, principal, assignment_id)
    if assignment["assignment_status"] == "closed":
        raise PlanogramExecutionError("closed_assignment_rejects_new_compliance")
    if assignment["plan_status"] != "approved" or not assignment["physical_truth_attested"]:
        raise PlanogramExecutionError("compliance_requires_approved_attested_plan")

    try:
        context = await get_promotion_context_in_session(
            session,
            tenant_id=str(principal.tenant_id),
            promotion_id=str(field_promotion_id),
        )
    except FieldPromotionError as exc:
        raise PlanogramExecutionError(str(exc)) from exc

    if str(context.get("consumer_module")) != "planogram":
        raise PlanogramExecutionError("promotion_consumer_must_be_planogram")
    if str(context.get("adapter_key")) != COMPLIANCE_ADAPTER:
        raise PlanogramExecutionError("promotion_adapter_must_be_planogram_compliance_v1")
    if str(context.get("field_decision") or "") != "approve":
        raise PlanogramExecutionError("compliance_promotion_requires_field_approval")
    if str(context.get("location_id")) != str(assignment["store_code"]):
        raise PlanogramExecutionError("promotion_location_does_not_match_assignment_store")

    candidate = dict(context["candidate_payload"])
    if str(candidate.get("plan_version_id")) != str(assignment["plan_version_id"]):
        raise PlanogramExecutionError("promotion_plan_version_does_not_match_assignment")

    evaluation = evaluate_compliance(dict(assignment["plan_payload"]), candidate)
    observation = await insert_compliance_observation(
        session,
        principal,
        assignment_id=assignment_id,
        plan_version_id=assignment["plan_version_id"],
        field_promotion_id=field_promotion_id,
        candidate_fingerprint=str(context["candidate_fingerprint"]),
        evaluation=evaluation,
    )

    receipt: dict[str, Any] | None = None
    if context.get("consumer_receipt_id") is None:
        try:
            receipt = await record_consumer_receipt_in_session(
                session,
                tenant_id=str(principal.tenant_id),
                actor_subject=principal.subject,
                context=context,
                consumer_module="planogram",
                destination_candidate_ref=f"planogram-compliance:{observation['id']}",
            )
        except FieldPromotionError as exc:
            raise PlanogramExecutionError(str(exc)) from exc
    elif not observation.get("idempotent_replay"):
        raise PlanogramExecutionError("consumer_receipt_exists_without_matching_observation")

    return {
        "assignment_id": str(assignment_id),
        "plan_version_id": str(assignment["plan_version_id"]),
        "store_code": assignment["store_code"],
        "plan_fingerprint": assignment["plan_fingerprint"],
        "observation": observation,
        "consumer_receipt": receipt,
        "idempotent_replay": bool(observation.get("idempotent_replay")),
        "truth_boundary": {
            "field_evidence_is_planogram_truth": False,
            "approved_plan_is_execution_baseline": True,
            "compliance_observation_is_append_only": True,
        },
    }
