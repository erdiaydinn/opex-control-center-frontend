"""Read-only tenant-bound Workforce active-shift authority.

This module is intentionally small: operational modules may ask whether a
canonical employee is currently checked in at one of their authorized
warehouses, but they may not read or mutate Workforce's in-process globals.
Production truth comes from the tenant-scoped PostgreSQL snapshot only.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def resolve_active_shift(
    tenant_id: str,
    employee_id: str,
    warehouse_ids: frozenset[str] | set[str] | tuple[str, ...],
) -> ActiveShiftAttestation | None:
    """Return exactly one durable open shift, otherwise deny or return no shift.

    A valid operational shift requires the same tenant, employee and warehouse,
    a still-open attendance row, and a linked shift whose canonical status is
    ``Vardiyada``. Multiple matching open shifts are treated as corrupted or
    ambiguous authority and fail closed instead of selecting one arbitrarily.
    """

    requested_tenant = str(tenant_id).strip()
    requested_employee = str(employee_id).strip()
    if not requested_tenant or not requested_employee:
        raise PermissionError("Tenant ve canonical Employee ID aktif vardiya için zorunludur.")

    configured_tenant = persistence.tenant_id()
    if requested_tenant != configured_tenant:
        raise PermissionError("Workforce tenant ile Inventory tenant eşleşmiyor.")
    if not persistence.ENABLED:
        raise ActiveShiftAuthorityError("Workforce PostgreSQL authority kullanılamıyor.")

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

    row = rows[0]
    attendance_id, shift_id, resolved_employee, checked_in_at, warehouse_id = row
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
