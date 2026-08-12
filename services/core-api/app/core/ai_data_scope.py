"""Canonical, fail-closed data scope for Jarvis read tools.

The scope originates only from DB-backed role_permissions.scope records.
It is deliberately narrow: V1 supports an explicit finite list of canonical
store names. Empty scope, wildcards and unknown keys are rejected instead of
being interpreted as tenant-wide or global access.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AI_DATA_SCOPE_VERSION = 1
AI_DATA_SCOPE_ROOT_KEY = "ai_data_scope"
AI_DATA_SCOPE_MAX_STORES = 250
AI_DATA_SCOPE_MAX_STORE_NAME_LENGTH = 200

_BLOCKED_SCOPE_NAMES = frozenset(
    {
        "*",
        "all",
        "all stores",
        "all_stores",
        "__all__",
    }
)


class AiDataScopeError(PermissionError):
    """Base denial for an unusable authoritative AI data scope."""


class AiDataScopeInvalid(AiDataScopeError):
    """The persisted scope is malformed, ambiguous or unsupported."""


class AiDataScopeEmpty(AiDataScopeError):
    """The persisted scope resolves to no authorized data."""


class AiDataScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal[1] = AI_DATA_SCOPE_VERSION
    store_names: tuple[str, ...]


def _normalize_store_name(value: Any) -> str:
    if not isinstance(value, str):
        raise AiDataScopeInvalid(
            "AI data scope store name must be text"
        )

    normalized = unicodedata.normalize(
        "NFC",
        " ".join(value.split()),
    )

    if not normalized:
        raise AiDataScopeInvalid(
            "AI data scope store name is empty"
        )

    if len(normalized) > AI_DATA_SCOPE_MAX_STORE_NAME_LENGTH:
        raise AiDataScopeInvalid(
            "AI data scope store name is too long"
        )

    lowered = normalized.casefold()
    if (
        lowered in _BLOCKED_SCOPE_NAMES
        or "*" in normalized
        or "%" in normalized
    ):
        raise AiDataScopeInvalid(
            "AI data scope wildcard is forbidden"
        )

    return normalized


def _normalize_store_names(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise AiDataScopeInvalid(
            "AI data scope store_names must be a list"
        )

    if not 1 <= len(value) <= AI_DATA_SCOPE_MAX_STORES:
        raise AiDataScopeEmpty(
            "AI data scope must contain a bounded store list"
        )

    names = tuple(
        _normalize_store_name(item)
        for item in value
    )

    normalized_keys = [
        item.casefold()
        for item in names
    ]

    if len(set(normalized_keys)) != len(normalized_keys):
        raise AiDataScopeInvalid(
            "AI data scope contains duplicate store names"
        )

    return tuple(
        sorted(
            names,
            key=lambda item: (
                item.casefold(),
                item,
            ),
        )
    )


def parse_ai_data_scope(
    permission_scope: Mapping[str, Any],
) -> AiDataScope:
    """Parse one DB-backed role permission scope with no widening defaults."""

    if not isinstance(permission_scope, Mapping):
        raise AiDataScopeInvalid(
            "AI permission scope must be an object"
        )

    if set(permission_scope) != {AI_DATA_SCOPE_ROOT_KEY}:
        raise AiDataScopeInvalid(
            "AI permission scope keys are unsupported"
        )

    raw = permission_scope[AI_DATA_SCOPE_ROOT_KEY]
    if not isinstance(raw, Mapping):
        raise AiDataScopeInvalid(
            "ai_data_scope must be an object"
        )

    if set(raw) != {"version", "store_names"}:
        raise AiDataScopeInvalid(
            "ai_data_scope keys are unsupported"
        )

    version = raw.get("version")
    if (
        isinstance(version, bool)
        or version != AI_DATA_SCOPE_VERSION
    ):
        raise AiDataScopeInvalid(
            "ai_data_scope version is unsupported"
        )

    return AiDataScope(
        version=AI_DATA_SCOPE_VERSION,
        store_names=_normalize_store_names(
            raw.get("store_names")
        ),
    )


def union_ai_data_scopes(
    scopes: Iterable[AiDataScope],
) -> AiDataScope:
    """Combine additive role grants for the same permission."""

    scope_list = tuple(scopes)
    if not scope_list:
        raise AiDataScopeEmpty(
            "AI permission has no usable data scope"
        )

    stores: dict[str, str] = {}
    for scope in scope_list:
        for store_name in scope.store_names:
            key = store_name.casefold()
            existing = stores.get(key)
            if existing is not None and existing != store_name:
                raise AiDataScopeInvalid(
                    "AI data scope store casing is ambiguous"
                )
            stores[key] = store_name

    if not stores:
        raise AiDataScopeEmpty(
            "AI permission data scope is empty"
        )

    if len(stores) > AI_DATA_SCOPE_MAX_STORES:
        raise AiDataScopeInvalid(
            "Combined AI data scope is too large"
        )

    return AiDataScope(
        store_names=tuple(
            sorted(
                stores.values(),
                key=lambda item: (
                    item.casefold(),
                    item,
                ),
            )
        )
    )


def intersect_ai_data_scopes(
    scopes: Iterable[AiDataScope],
) -> AiDataScope:
    """Intersect independently required permission scopes for one tool."""

    scope_list = tuple(scopes)
    if not scope_list:
        raise AiDataScopeEmpty(
            "AI tool has no data scope"
        )

    by_scope = [
        {
            store_name.casefold(): store_name
            for store_name in scope.store_names
        }
        for scope in scope_list
    ]

    common = set(by_scope[0])
    for mapping in by_scope[1:]:
        common.intersection_update(mapping)

    if not common:
        raise AiDataScopeEmpty(
            "Required AI permission scopes do not overlap"
        )

    canonical: list[str] = []
    for key in common:
        variants = {
            mapping[key]
            for mapping in by_scope
            if key in mapping
        }
        if len(variants) != 1:
            raise AiDataScopeInvalid(
                "AI data scope store casing is ambiguous"
            )
        canonical.append(next(iter(variants)))

    return AiDataScope(
        store_names=tuple(
            sorted(
                canonical,
                key=lambda item: (
                    item.casefold(),
                    item,
                ),
            )
        )
    )


def ai_data_scope_fingerprint(scope: AiDataScope) -> str:
    payload = {
        "version": scope.version,
        "store_names": scope.store_names,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
