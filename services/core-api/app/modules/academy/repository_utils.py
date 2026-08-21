import hashlib
import json

from app.core.security import Principal


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def roles_json(principal: Principal) -> str:
    return json_text(sorted({role.strip().lower() for role in principal.roles if role.strip()}))


def stable_fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
