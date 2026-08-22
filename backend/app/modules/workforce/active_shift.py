"""Read-only tenant-bound Workforce active-shift authority.

Operational modules may ask whether a canonical employee is currently checked
in or whether a signed/offline event occurred inside one specific durable shift,
but they may not read or mutate Workforce's in-process globals. Production
truth comes from the tenant-scoped PostgreSQL snapshot only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from . import persistence


class ActiveShiftAuthorityError(RuntimeError):
    """Raised when active-shift truth cannot be resolved safely."""


@dataclass(frozen=True)
class ActiveShiftAttestation:
    tenant_id: str
    employee_id: str
    warehouse_id: str
    shift_id: str
    attendance_id: str
    checked_in_at: str


def _normalized_warehouses(warehouse_ids: frozenset[str] | set[str] | tuple[str, ...]) -> list[str]:
    values = sorted({str(value).strip().lower() for value in warehouse_ids if str(value).strip()})
    if not values:
        raise PermissionError("Aktif vardiya doğrulaması için depo kapsamı zorunludur.")
    return values


def _authority_context(tenant_id: str, employee_id: str) -> tuple[str, str]:
    requested_tenant = str(tenant_id).strip()
    requested_employee = str(employee_id).strip()
    if not requested_tenant or not requested_employee:
        raise PermissionError("Tenant ve canonical Employee ID aktif vardiya için zorunludur.")
    configured_tenant = persistence.tenant_id()
    if requested_tenant != configured_tenant:
        raise PermissionError("Workforce tenant ile operasyon tenant eşleşmiyor.")
    if not persistence.ENABLED:
        raise ActiveShiftAuthorityError("Workforce PostgreSQL authority kullanılamıyor.")
    return configured_tenant, requested_employee


def _parse_instant(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ActiveShiftAuthorityError(f"Workforce {field} zamanı geçersiz.") from error
    if parsed.tzinfo is None:
        raise ActiveShiftAuthorityError(f"Workforce {field} zamanı timezone içermelidir.")
    return parsed.astimezone(UTC)


def resolve_active_shift(
    tenant_id: str,
    employee_id: str,
    warehouse_ids: frozenset[str] | set[str] | tuple[str, ...],
) -> ActiveShiftAttestation | None:
    """Return exactly one durable open shift, otherwise deny or return no shift."""

    configured_tenant, requested_employee = _authority_context(tenant_id, employee_id)
    warehouses = _normalized_warehouses(warehouse_ids)
    try:
        with persistence.connection() as database, database.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute(
                "SELECT set_config('app.workforce_tenant', %s, true)",
                (configured_tenant,),
            )
            cursor.execute(
                """SELECT
                     a.payload->>'id' AS attendance_id,
                     a.payload->>'shift_id' AS shift_id,
                     a.payload->>'person_id' AS employee_id,
                     a.payload->>'check_in' AS checked_in_at,
                     s.payload->>'warehouse_id' AS warehouse_id
                   FROM workforce_entities a
                   JOIN workforce_entities s
                     ON s.tenant_id=a.tenant_id
                    AND s.kind='shifts'
                    AND s.entity_id=a.payload->>'shift_id'
                   WHERE a.tenant_id=%s
                     AND a.kind='attendance'
                     AND a.payload->>'person_id'=%s
                     AND a.payload->>'check_in' IS NOT NULL
                     AND (a.payload->>'check_out' IS NULL OR a.payload->>'check_out'='—')
                     AND a.payload->>'status'='Vardiyada'
                     AND s.payload->>'person_id'=%s
                     AND s.payload->>'status'='Vardiyada'
                     AND lower(trim(s.payload->>'warehouse_id'))=ANY(%s)
                   ORDER BY a.payload->>'check_in' DESC
                   LIMIT 2""",
                (configured_tenant, requested_employee, requested_employee, warehouses),
            )
            rows = cursor.fetchall()
    except PermissionError:
        raise
    except Exception as error:
        raise ActiveShiftAuthorityError(
            "Workforce aktif vardiya authority okunamadı."
        ) from error

    if not rows:
        return None
    if len(rows) != 1:
        raise ActiveShiftAuthorityError(
            "Bir çalışan için birden fazla açık vardiya bulundu; görevler kapatıldı."
        )

    attendance_id, shift_id, resolved_employee, checked_in_at, warehouse_id = rows[0]
    if (
        not attendance_id
        or not shift_id
        or str(resolved_employee) != requested_employee
        or not checked_in_at
        or not warehouse_id
    ):
        raise ActiveShiftAuthorityError("Workforce aktif vardiya kaydı eksik veya bozuk.")

    return ActiveShiftAttestation(
        tenant_id=configured_tenant,
        employee_id=requested_employee,
        warehouse_id=str(warehouse_id),
        shift_id=str(shift_id),
        attendance_id=str(attendance_id),
        checked_in_at=str(checked_in_at),
    )


def attest_shift_at_event(
    tenant_id: str,
    employee_id: str,
    warehouse_id: str,
    shift_id: str,
    occurred_at: str,
) -> ActiveShiftAttestation | None:
    """Verify an offline event occurred while its server-issued shift was open.

    This is historical attestation, not a requirement that the shift is still
    open at reconnect time. It allows a valid offline count to sync after
    checkout while rejecting events timestamped outside the attendance window.
    """

    configured_tenant, requested_employee = _authority_context(tenant_id, employee_id)
    requested_warehouse = str(warehouse_id).strip().lower()
    requested_shift = str(shift_id).strip()
    if not requested_warehouse or not requested_shift:
        raise PermissionError("Depo ve server-issued active shift kimliği zorunludur.")
    event_time = _parse_instant(occurred_at, "event")
    if event_time > datetime.now(UTC) + timedelta(minutes=2):
        raise PermissionError("Event zamanı gelecekte olamaz.")

    try:
        with persistence.connection() as database, database.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute(
                "SELECT set_config('app.workforce_tenant', %s, true)",
                (configured_tenant,),
            )
            cursor.execute(
                """SELECT
                     a.payload->>'id' AS attendance_id,
                     a.payload->>'shift_id' AS shift_id,
                     a.payload->>'person_id' AS employee_id,
                     a.payload->>'check_in' AS checked_in_at,
                     a.payload->>'check_out' AS checked_out_at,
                     s.payload->>'warehouse_id' AS warehouse_id,
                     s.payload->>'status' AS shift_status
                   FROM workforce_entities a
                   JOIN workforce_entities s
                     ON s.tenant_id=a.tenant_id
                    AND s.kind='shifts'
                    AND s.entity_id=a.payload->>'shift_id'
                   WHERE a.tenant_id=%s
                     AND a.kind='attendance'
                     AND a.payload->>'person_id'=%s
                     AND a.payload->>'shift_id'=%s
                     AND a.payload->>'check_in' IS NOT NULL
                     AND s.payload->>'person_id'=%s
                     AND lower(trim(s.payload->>'warehouse_id'))=%s
                     AND s.payload->>'status'<>'İptal'
                   ORDER BY a.payload->>'check_in' DESC
                   LIMIT 2""",
                (
                    configured_tenant,
                    requested_employee,
                    requested_shift,
                    requested_employee,
                    requested_warehouse,
                ),
            )
            rows = cursor.fetchall()
    except PermissionError:
        raise
    except Exception as error:
        raise ActiveShiftAuthorityError(
            "Workforce event vardiya authority okunamadı."
        ) from error

    if not rows:
        return None
    if len(rows) != 1:
        raise ActiveShiftAuthorityError(
            "Event vardiyası birden fazla attendance kaydına bağlı; event kapatıldı."
        )

    (
        attendance_id,
        resolved_shift,
        resolved_employee,
        checked_in_at,
        checked_out_at,
        resolved_warehouse,
        _shift_status,
    ) = rows[0]
    if (
        not attendance_id
        or str(resolved_shift) != requested_shift
        or str(resolved_employee) != requested_employee
        or not checked_in_at
        or str(resolved_warehouse).strip().lower() != requested_warehouse
    ):
        raise ActiveShiftAuthorityError("Workforce event vardiya kaydı eksik veya bozuk.")

    check_in = _parse_instant(str(checked_in_at), "check-in")
    if event_time < check_in:
        return None
    if checked_out_at not in (None, "", "—"):
        check_out = _parse_instant(str(checked_out_at), "check-out")
        if event_time > check_out:
            return None

    return ActiveShiftAttestation(
        tenant_id=configured_tenant,
        employee_id=requested_employee,
        warehouse_id=str(resolved_warehouse),
        shift_id=requested_shift,
        attendance_id=str(attendance_id),
        checked_in_at=str(checked_in_at),
    )
