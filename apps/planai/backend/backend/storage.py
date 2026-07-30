import json
import os
from copy import deepcopy
from datetime import datetime


DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def now_iso():
    return datetime.utcnow().isoformat() + "Z"


def path(name):
    return os.path.join(DATA_DIR, name)


def load_json(filename, default):
    file_path = path(filename)

    if not os.path.exists(file_path):
        save_json(filename, default)
        return deepcopy(default)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return deepcopy(default)


def save_json(filename, data):
    with open(path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_json_list(filename, record):
    data = load_json(filename, [])
    data.append(record)
    save_json(filename, data)
    return record


def next_id(filename):
    data = load_json(filename, [])
    if not data:
        return 1
    return max(int(x.get("id", 0)) for x in data) + 1


# ---------- USERS ----------

def load_users():
    return load_json("users.json", {
        "erdi": {"password": "1234", "role": "ADMIN"},
        "demo": {"password": "1234", "role": "USER"},
        "mod": {"password": "1234", "role": "MODERATOR"}
    })


def save_users(users):
    save_json("users.json", users)


# ---------- CHANGE REQUESTS ----------

def load_change_requests():
    return load_json("change_requests.json", [])


def save_change_requests(records):
    save_json("change_requests.json", records)


# ---------- OVERRIDES ----------

def load_overrides():
    return load_json("overrides.json", {"products": {}, "stores": {}})


def save_overrides(overrides):
    save_json("overrides.json", overrides)


# ---------- STORE CONFIGS ----------

def load_store_configs():
    return load_json("store_configs.json", {})


def save_store_configs(configs):
    save_json("store_configs.json", configs)


def get_store_config(store_code):
    configs = load_store_configs()
    return configs.get(str(store_code).upper())


def save_store_config(store_code, config):
    configs = load_store_configs()
    configs[str(store_code).upper()] = {
        **config,
        "store_code": str(store_code).upper(),
        "updated_at": now_iso(),
    }
    save_store_configs(configs)
    return configs[str(store_code).upper()]


# ---------- CONFIDENCE ----------

def load_confidence():
    return load_json("confidence.json", {
        "global_score": 100,
        "history": []
    })


def save_confidence(data):
    save_json("confidence.json", data)