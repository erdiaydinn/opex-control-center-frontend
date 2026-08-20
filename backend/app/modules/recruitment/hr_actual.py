from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from app.modules.workforce import persistence
from app.modules.workforce.service import list_warehouses, resolve_person_identity

from .service import RecruitmentRuleError, evaluate


_COLLECTION = "recruitment_hr_actual"
_STAFF_CODES = {"STORE_STAFF", "ASSISTANT_MANAGER", "STORE_SUPPORT"}


def _normalize(value: object | None) -> str:
    return str(value or "").strip().casefold().replace("i̇", "i")


def _position_code(value: object | None) -> str:
    raw = _normalize(value).replace("_", " ").replace("-", " ")
    if (
        raw in {"warehouse manager", "store manager", "depo müdürü", "depo muduru", "mağaza müdürü", "magaza muduru"}
        or ("müdür" in raw or "mudur" in raw or "manager" in raw)
        and not any(token in raw for token in {"yardım", "yardim", "assistant"})
    ):
        return "STORE_MANAGER"
    if any(token in raw for token in {"yardım", "yardim", "assistant"}):
        return "ASSISTANT_MANAGER"
    if any(token in raw for token in {"destek", "support"}):
        return "STORE_SUPPORT"
    return "STORE_STAFF"


def _warehouse_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for warehouse in list_warehouses():
        aliases = {
            warehouse.get("id"), warehouse.get("name"), warehouse.get("code"),
            str(warehouse.get("name") or "").split(" (")[0],
        }
        for alias in aliases:
            if alias:
                index[_normalize(alias)] = warehouse
    return index


def _canonical_warehouse(value: object | None, index: dict[str, dict]) -> tuple[str, str | None, bool]:
    raw = str(value or "").strip()
    warehouse = index.get(_normalize(raw))
    if warehouse is None:
        warehouse = index.get(_normalize(raw.split(" (")[0]))
    if warehouse is None:
        return raw, None, False
    return str(warehouse.get("name") or raw), str(warehouse.get("id") or "") or None, True


def _identity(row: dict) -> tuple[dict | None, str]:
    tckn = str(row.get("tckn") or "").strip()
    employee_id = str(row.get("employee_id") or "").strip()
    if tckn:
        person = resolve_person_identity(tckn, "TC")
        if person:
            return person, "TCKN"
    if employee_id:
        person = resolve_person_identity(employee_id, "EMPLOYEE_ID")
        if person:
            return person, "EMPLOYEE_ID"
    return None, "UNMATCHED"


def import_snapshot(payload: dict, actor: str) -> dict:
    """Persist a minimized, versioned HR Actual snapshot.

    TCKN is accepted only transiently for canonical Employee Master resolution and
    is never stored in the snapshot or returned by this module. The current
    collection revision is loaded before the CAS write so a process restart does
    not turn a valid next import into a false stale-write conflict.
    """
    rows = list(payload.get("rows") or [])
    if not rows:
        raise RecruitmentRuleError("HR Actual dosyasında işlenebilir kayıt bulunamadı.")

    # Prime the persistence revision from the authoritative store before writing.
    # persist_snapshot_with_audit still performs optimistic CAS, so concurrent
    # imports remain fail-closed rather than silently overwriting one another.
    persistence.load_collection(_COLLECTION)

    warehouse_index = _warehouse_index()
    sanitized: list[dict] = []
    matched = unmatched = active_rows = 0
    fte_total = 0.0

    for row_number, row in enumerate(rows, start=2):
        source_employee_id = str(row.get("employee_id") or "").strip()
        person, identity_method = _identity(row)
        warehouse_name, warehouse_id, warehouse_matched = _canonical_warehouse(row.get("warehouse"), warehouse_index)
        source_position = str(row.get("position") or "").strip()
        position_code = _position_code(source_position)
        active = bool(row.get("active", True))
        fte = round(max(0.0, min(2.0, float(row.get("fte", 1) or 0))), 4)
        canonical_employee_id = str((person or {}).get("employee_id") or "") or None
        employee_master_warehouse = str((person or {}).get("warehouse") or (person or {}).get("warehouse_id") or "").strip()
        warehouse_conflict = bool(
            person and warehouse_name and employee_master_warehouse
            and _normalize(warehouse_name) not in {_normalize(employee_master_warehouse), _normalize(employee_master_warehouse).split(" (")[0]}
            and _normalize(employee_master_warehouse) not in {_normalize(warehouse_id)}
        )
        if person:
            matched += 1
        else:
            unmatched += 1
        if active:
            active_rows += 1
            fte_total += fte
        sanitized.append({
            "row_number": row_number,
            "source_employee_id": source_employee_id or None,
            "employee_id": canonical_employee_id,
            "identity_method": identity_method,
            "warehouse": warehouse_name,
            "warehouse_id": warehouse_id,
            "warehouse_matched": warehouse_matched,
            "warehouse_conflict": warehouse_conflict,
            "position_code": position_code,
            "source_position": source_position or None,
            "fte": fte,
            "active": active,
            "matched": bool(person),
        })

    canonical_for_hash = [
        {
            "source_employee_id": row["source_employee_id"],
            "warehouse": row["warehouse"],
            "position_code": row["position_code"],
            "fte": row["fte"],
            "active": row["active"],
        }
        for row in sanitized
    ]
    source_sha256 = sha256(
        json.dumps(canonical_for_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    imported_at = datetime.now(UTC).isoformat()
    snapshot = {
        "id": _COLLECTION,
        "source_name": str(payload.get("source_name") or "HR Actual").strip()[:240],
        "source_sha256": source_sha256,
        "as_of": str(payload.get("as_of") or imported_at[:10]),
        "imported_at": imported_at,
        "imported_by": actor,
        "source_rows": len(sanitized),
        "active_rows": active_rows,
        "active_fte": round(fte_total, 2),
        "matched_rows": matched,
        "unmatched_rows": unmatched,
        "match_rate": round((matched / len(sanitized)) * 100, 1) if sanitized else 0.0,
        "rows": sanitized,
    }
    persistence.persist_snapshot_with_audit(
        {_COLLECTION: [snapshot]},
        "RECRUITMENT_HR_ACTUAL_IMPORTED",
        actor,
        source_name=snapshot["source_name"],
        source_sha256=source_sha256,
        source_rows=len(sanitized),
        active_rows=active_rows,
        matched_rows=matched,
        unmatched_rows=unmatched,
    )
    return snapshot_summary(snapshot)


def latest_snapshot() -> dict | None:
    rows = persistence.load_collection(_COLLECTION)
    return rows[0] if rows else None


def snapshot_summary(snapshot: dict | None = None) -> dict | None:
    current = snapshot or latest_snapshot()
    if not current:
        return None
    return {
        "source_name": current.get("source_name"),
        "source_sha256": current.get("source_sha256"),
        "as_of": current.get("as_of"),
        "imported_at": current.get("imported_at"),
        "source_rows": int(current.get("source_rows", 0)),
        "active_rows": int(current.get("active_rows", 0)),
        "active_fte": float(current.get("active_fte", 0)),
        "matched_rows": int(current.get("matched_rows", 0)),
        "unmatched_rows": int(current.get("unmatched_rows", 0)),
        "match_rate": float(current.get("match_rate", 0)),
    }


def enrich_evaluation(evaluation: dict) -> dict:
    snapshot = latest_snapshot()
    if not snapshot:
        return {
            **evaluation,
            "hr_actual": None,
            "hr_actual_fte": None,
            "hr_actual_unmatched": None,
            "hr_actual_delta": None,
            "hr_actual_as_of": None,
            "hr_actual_source": None,
            "actual_authority": "EMPLOYEE_MASTER_FALLBACK",
            "decision_actual_source": "EMPLOYEE_MASTER",
        }

    warehouse_name = _normalize(evaluation.get("warehouse_name"))
    position_code = str(evaluation.get("position_code") or "STORE_STAFF")
    wanted_codes = {"STORE_MANAGER"} if position_code == "STORE_MANAGER" else _STAFF_CODES
    rows = [
        row for row in snapshot.get("rows", [])
        if row.get("active", True)
        and _normalize(row.get("warehouse")) == warehouse_name
        and row.get("position_code") in wanted_codes
    ]
    hr_actual = len(rows)
    hr_fte = round(sum(float(row.get("fte", 1) or 0) for row in rows), 2)
    unmatched = sum(not row.get("matched", False) for row in rows)
    return {
        **evaluation,
        "hr_actual": hr_actual,
        "hr_actual_fte": hr_fte,
        "hr_actual_unmatched": unmatched,
        "hr_actual_delta": int(evaluation.get("active", 0)) - hr_actual,
        "hr_actual_as_of": snapshot.get("as_of"),
        "hr_actual_source": snapshot.get("source_name"),
        "actual_authority": "HR_SNAPSHOT",
        "decision_actual_source": "EMPLOYEE_MASTER",
    }


def build_dashboard(scoped_norms: list[dict], scoped_requests: list[dict]) -> dict:
    warehouse_rows: list[dict] = []
    for norm in scoped_norms:
        try:
            warehouse_rows.append(enrich_evaluation(evaluate(norm["warehouse"], "STORE_STAFF", 1)))
        except RecruitmentRuleError:
            continue
    return {
        "pending": sum(row.get("status") == "PENDING_APPROVAL" for row in scoped_requests),
        "approved": sum(row.get("status") == "APPROVED" for row in scoped_requests),
        "rejected": sum(row.get("status") == "REJECTED" for row in scoped_requests),
        "evidence_required": sum(row.get("status") == "EVIDENCE_REQUIRED" for row in scoped_requests),
        "norm_gap_warehouses": sum(int(row.get("available", 0)) > 0 for row in warehouse_rows),
        "warehouse_rows": sorted(
            warehouse_rows,
            key=lambda row: (int(row.get("available", 0)), int(row.get("hr_actual_unmatched") or 0)),
            reverse=True,
        ),
    }