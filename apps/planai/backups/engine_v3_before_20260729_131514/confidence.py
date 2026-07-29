from storage import load_confidence, save_confidence, now_iso


def update_confidence(action, success, username=None, store_code=None, reason=None):
    data = load_confidence()

    if success:
        data["global_score"] = min(100, data.get("global_score", 100) + 1)
    else:
        data["global_score"] = max(0, data.get("global_score", 100) - 2)

    data["history"].append({
        "created_at": now_iso(),
        "username": username,
        "store_code": store_code,
        "action": action,
        "success": success,
        "reason": reason
    })

    save_confidence(data)
    return data


def get_confidence():
    return load_confidence()