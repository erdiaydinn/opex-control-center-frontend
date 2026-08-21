"""Permission- and scope-guarded Time Off parsing boundary.

Raw TCKN may exist inside the uploaded file, but it is consumed only on the
backend to resolve an existing Employee Master identity. It is never returned
to the browser and never creates a new employee.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .authorization import is_action_allowed
from .service import resolve_person_identity
from .timeoff_parser import TimeOffParseError, parse_timeoff_payload


router = APIRouter(prefix="/workforce/time-off", tags=["Workforce"])


class TimeOffParseRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=17_000_000)


def _require_import(role: str, permissions: str) -> None:
    if not is_action_allowed(role, permissions, "importTimeOff"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için importTimeOff yetkisi gerekir.")


def _canonicalize_identity(row: dict) -> tuple[dict | None, bool, dict | None]:
    """Return a browser-safe row, resolution state and resolved Employee Master."""
    source = str(row.get("source_person_id") or row.get("person_id") or "").strip()
    national_id = str(row.pop("national_id", "") or "").strip()
    person = None
    method = ""
    if source:
        person = resolve_person_identity(source, "EMPLOYEE_ID")
        method = "Employee ID"
        if person is None:
            person = resolve_person_identity(source, "ROSTER_ID")
            method = "Roster ID"
    if person is None and len(national_id) == 11:
        person = resolve_person_identity(national_id, "TC")
        method = "TC"
    if person is not None:
        canonical = str(person["employee_id"])
        row.update({
            "person_id": canonical,
            "source_person_id": canonical,
            "person_name": row.get("person_name") or person.get("full_name", ""),
            "identity_method": "EMPLOYEE_ID",
            "identity_resolution": method,
        })
        return row, True, person
    if source:
        row.update({
            "person_id": source,
            "source_person_id": source,
            "identity_method": "",
            "identity_resolution": "UNRESOLVED_NON_SENSITIVE_ID",
        })
        return row, False, None
    # A TCKN-only row that does not match Employee Master cannot safely be sent
    # to the browser. It stays unmatched rather than becoming a new employee.
    return None, False, None


@router.post("/parse")
def parse_time_off(
    payload: TimeOffParseRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_import(x_opex_role, x_opex_permissions)
    # Import routing shares the canonical Workforce scope authority. The import
    # endpoint may be granted to warehouse managers, but parsing a file must not
    # become a cross-warehouse identity-discovery side channel.
    from .router import _row_warehouse_id, _warehouse_scope

    scope = _warehouse_scope(request, x_opex_role)
    try:
        parsed = parse_timeoff_payload(payload.file_name, payload.content_base64)
    except TimeOffParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    safe_rows = []
    resolved = 0
    identity_unmatched = 0
    sensitive_only_unmatched = 0
    scope_blocked = 0
    for source in parsed["rows"]:
        raw_had_only_sensitive_identity = not source.get("source_person_id") and bool(source.get("national_id"))
        safe, was_resolved, person = _canonicalize_identity(dict(source))
        if safe is None:
            identity_unmatched += 1
            sensitive_only_unmatched += int(raw_had_only_sensitive_identity)
            continue
        if scope is not None and (person is None or _row_warehouse_id(person) not in scope):
            scope_blocked += 1
            continue
        safe_rows.append(safe)
        resolved += int(was_resolved)
        identity_unmatched += int(not was_resolved)

    return {
        "rows": safe_rows,
        "source_count": parsed["source_count"],
        "invalid_count": parsed["invalid_count"],
        "identity_resolved_count": resolved,
        "identity_unmatched_count": identity_unmatched,
        "sensitive_only_unmatched_count": sensitive_only_unmatched,
        "scope_blocked_count": scope_blocked,
        "parser": parsed["parser"],
        "sensitive_data_exposed": False,
    }
