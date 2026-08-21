"""Employee Master capability and generic worksite metadata authority.

This extends the canonical Workforce Employee Master row; it does not create a
parallel employee identity model. Capability keys are operational eligibility
facts used by open-shift and planning engines.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime


class WorkforceCapabilityAuthorityError(ValueError):
    pass


def update_employee_capabilities(employee_id: str, payload: dict, actor: str) -> dict:
    # Lazy import prevents the capability authority from participating in module
    # initialization cycles while still mutating the canonical Employee Master.
    from . import service

    person = service.resolve_person_identity(str(employee_id), "EMPLOYEE_ID")
    if person is None:
        raise WorkforceCapabilityAuthorityError("Employee Master record was not found.")
    before = {
        "skill_keys": list(person.get("skill_keys") or []),
        "certification_keys": list(person.get("certification_keys") or []),
        "equipment_keys": list(person.get("equipment_keys") or []),
    }
    person["skill_keys"] = list(payload.get("skill_keys") or [])
    person["certification_keys"] = list(payload.get("certification_keys") or [])
    person["equipment_keys"] = list(payload.get("equipment_keys") or [])
    person["capability_updated_at"] = datetime.now(UTC).isoformat()
    person["capability_updated_by"] = actor
    service._append_audit(
        "EMPLOYEE_CAPABILITIES_UPDATED",
        actor,
        employee_id=str(person["employee_id"]),
        before=before,
        after={
            "skill_keys": person["skill_keys"],
            "certification_keys": person["certification_keys"],
            "equipment_keys": person["equipment_keys"],
        },
    )
    return deepcopy({
        "employee_id": str(person["employee_id"]),
        "skill_keys": person["skill_keys"],
        "certification_keys": person["certification_keys"],
        "equipment_keys": person["equipment_keys"],
        "updated_at": person["capability_updated_at"],
        "updated_by": actor,
    })


def update_worksite_type(worksite_id: str, location_type: str, actor: str) -> dict:
    from . import service

    existing = next(
        (row for row in service.list_warehouses() if str(row.get("id")) == str(worksite_id)),
        None,
    )
    if existing is None:
        raise WorkforceCapabilityAuthorityError("Worksite was not found.")
    record = service.upsert_warehouse(
        {**existing, "id": str(existing["id"]), "location_type": str(location_type)},
        actor,
    )
    return deepcopy(record)
