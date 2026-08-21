"""Fail-closed Hiring -> Workforce offboarding authority bridge.

The Recruitment case is not authoritative for employee access.  Closing an
Offboarding case must first project its effective end date into the canonical
Workforce Employee Master authority, which owns device access, future shifts,
notifications and corporate identity revocation requests.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.modules.workforce import service as workforce_service


class WorkforceOffboardingBridgeError(RuntimeError):
    pass


_ISTANBUL = ZoneInfo("Europe/Istanbul")
_ACTIVE_FUTURE_SHIFT_STATES = {"Atandı", "Yayınlandı"}


def _effective_date(effective_at: datetime) -> str:
    if effective_at.tzinfo is None:
        raise WorkforceOffboardingBridgeError("Offboarding effective_at timezone-aware olmalıdır.")
    return effective_at.astimezone(_ISTANBUL).date().isoformat()


def _active_future_shifts(employee_id: str, employment_end: str) -> list[dict]:
    return [
        row
        for row in workforce_service.list_shifts(employee_id)
        if str(row.get("date") or "") >= employment_end
        and row.get("status") in _ACTIVE_FUTURE_SHIFT_STATES
    ]


def apply_offboarding_to_workforce(
    employee_id: str,
    *,
    effective_at: datetime,
    actor: str,
) -> dict:
    """Schedule or execute the canonical Workforce employment exit.

    This call is deliberately idempotent.  If a prior retry already persisted
    exactly the same employment_end and all future shift/access invariants are
    satisfied, no second identity-revocation/audit mutation is emitted.
    """
    employee = str(employee_id or "").strip()
    if not employee:
        raise WorkforceOffboardingBridgeError("Offboarding employee_id boş olamaz.")
    employment_end = _effective_date(effective_at)
    today = datetime.now(_ISTANBUL).date().isoformat()

    person = workforce_service.resolve_person_identity(employee, "EMPLOYEE_ID")
    if person is None:
        raise WorkforceOffboardingBridgeError(
            "Offboarding Employee Master kaydı bulunamadı; Workforce authority doğrulanmadan case kapatılamaz."
        )

    existing_end = str(person.get("employment_end") or "").strip()
    if existing_end and existing_end != employment_end:
        raise WorkforceOffboardingBridgeError(
            f"Employee Master employment_end uyuşmuyor ({existing_end} != {employment_end}); reconciliation gerekli."
        )

    needs_apply = existing_end != employment_end
    if employment_end <= today and person.get("active", True):
        needs_apply = True
    if _active_future_shifts(employee, employment_end):
        needs_apply = True

    result = {
        "matched": 1,
        "unmatched": 0,
        "access_closures": 0,
        "revoked_devices": 0,
        "cancelled_shifts": 0,
        "identity_revocations_queued": 0,
    }
    if needs_apply:
        try:
            result = workforce_service.update_employment_lifecycle(
                [{
                    "person_id": employee,
                    "identity_method": "EMPLOYEE_ID",
                    "employment_end": employment_end,
                }],
                actor,
                "recruitment-offboarding-authority",
            )
        except workforce_service.WorkforceRuleError as error:
            raise WorkforceOffboardingBridgeError(str(error)) from error
        if int(result.get("matched") or 0) != 1 or int(result.get("unmatched") or 0) != 0:
            raise WorkforceOffboardingBridgeError("Workforce employment lifecycle projection doğrulanamadı.")

    authoritative = workforce_service.resolve_person_identity(employee, "EMPLOYEE_ID")
    if authoritative is None or str(authoritative.get("employment_end") or "") != employment_end:
        raise WorkforceOffboardingBridgeError("Employee Master employment_end commit sonrası doğrulanamadı.")
    if employment_end <= today and authoritative.get("active", True):
        raise WorkforceOffboardingBridgeError("Effective offboarding sonrası Employee Master hâlâ aktif.")

    active_future = _active_future_shifts(employee, employment_end)
    if active_future:
        raise WorkforceOffboardingBridgeError(
            "Offboarding sonrası effective date ve ilerisinde aktif Workforce vardiyası kaldı."
        )

    access_state = "DEACTIVATED" if employment_end <= today else "SCHEDULED"
    return {
        "employee_id": employee,
        "employment_end": employment_end,
        "access_state": access_state,
        "workforce_access_allowed": workforce_service.person_has_workforce_access(authoritative),
        "active_future_shifts": 0,
        "idempotent_replay": not needs_apply,
        "access_closures": int(result.get("access_closures") or 0),
        "revoked_devices": int(result.get("revoked_devices") or 0),
        "cancelled_shifts": int(result.get("cancelled_shifts") or 0),
        "identity_revocations_queued": int(result.get("identity_revocations_queued") or 0),
        "truth_boundary": "WORKFORCE_EMPLOYEE_MASTER_PLUS_SHIFT_AND_IDENTITY_REVOCATION_AUTHORITY",
    }
