from storage import get_store_config, save_store_config, load_store_configs
from permissions import evaluate_permission


def normalize_store_code(store_code):
    return str(store_code or "").strip().upper()


def get_config(store_code):
    store_code = normalize_store_code(store_code)
    config = get_store_config(store_code)

    if config:
        return {
            "found": True,
            "store_code": store_code,
            "config": config
        }

    return {
        "found": False,
        "store_code": store_code,
        "message": "Bu depo için kayıtlı config yok."
    }


def save_config(username, role, store_code, config):
    decision = evaluate_permission(role, "edit_shelf_count")

    if not decision["allowed"]:
        return {
            "success": False,
            "requires_approval": decision["requires_approval"],
            "message": decision["message"]
        }

    store_code = normalize_store_code(store_code)
    saved = save_store_config(store_code, {
        **config,
        "updated_by": username,
        "role": role
    })

    return {
        "success": True,
        "store_code": store_code,
        "config": saved
    }


def list_configs():
    return load_store_configs()