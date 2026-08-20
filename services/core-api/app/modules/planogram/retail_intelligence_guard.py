"""Fail-closed payload guard for Planogram retail-intelligence previews."""

from __future__ import annotations

import re
from typing import Any

MAX_DEPTH = 12
MAX_NODES = 250_000
FORBIDDEN_IDENTITY_KEYS = {
    "customer",
    "customer_id",
    "customer_name",
    "email",
    "email_address",
    "phone",
    "phone_number",
    "mobile",
    "address",
    "full_name",
    "first_name",
    "last_name",
    "order_id",
    "order_code",
    "payment_token",
    "card_number",
    "user_email",
    "user_id",
}


def _key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


def retail_payload_blockers(payload: Any) -> list[str]:
    blockers: list[str] = []
    nodes = 0

    def visit(value: Any, path: str, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            blockers.append("payload_node_limit_exceeded")
            return
        if depth > MAX_DEPTH:
            blockers.append("payload_depth_limit_exceeded")
            return
        if isinstance(value, dict):
            for raw_key, nested in value.items():
                normalized = _key(raw_key)
                if normalized in FORBIDDEN_IDENTITY_KEYS:
                    blockers.append(f"forbidden_identity_key:{path}.{normalized}")
                    continue
                visit(nested, f"{path}.{normalized or 'key'}", depth + 1)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, f"{path}[{index}]", depth + 1)

    visit(payload, "payload", 0)
    return list(dict.fromkeys(blockers))


def assert_retail_payload_safe(payload: Any) -> None:
    blockers = retail_payload_blockers(payload)
    if blockers:
        raise ValueError(blockers[0])
