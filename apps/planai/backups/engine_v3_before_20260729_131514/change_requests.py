from datetime import datetime
from permissions import evaluate_permission
from overrides import apply_product_override

CHANGE_REQUESTS = []


def now_iso():
    return datetime.utcnow().isoformat() + "Z"


def submit_change(username, role, store_code, action, payload):
    decision = evaluate_permission(role, action)

    record = {
        "id": len(CHANGE_REQUESTS) + 1,
        "created_at": now_iso(),
        "username": username,
        "role": role,
        "store_code": store_code,
        "action": action,
        "payload": payload,
        "status": "PENDING",
    }

    if decision["allowed"]:
        record["status"] = "APPROVED_AUTO"
        apply_override_logic(record)

    elif decision["requires_approval"]:
        record["status"] = "PENDING_APPROVAL"

    else:
        record["status"] = "REJECTED"

    CHANGE_REQUESTS.append(record)
    return record


def apply_override_logic(record):
    if record["action"] == "edit_product_dimension":
        sku = record["payload"].get("sku")
        if sku:
            apply_product_override(
                sku,
                {
                    "width_cm": record["payload"].get("new_width_cm")
                }
            )


def approve_change(change_id, approver_username, approver_role):
    for r in CHANGE_REQUESTS:
        if r["id"] == change_id:
            r["status"] = "APPROVED"
            apply_override_logic(r)
            return r

    return {"error": "not found"}


def list_change_requests():
    return CHANGE_REQUESTS