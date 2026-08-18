from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.shared_platform.contracts import IntegrationContract, SearchDocument


@dataclass(frozen=True)
class SearchPrincipal:
    permissions: frozenset[str]


def visible_search_documents(
    principal: SearchPrincipal,
    documents: Sequence[SearchDocument],
) -> tuple[SearchDocument, ...]:
    """Only permission-authorized documents with provenance may enter results."""

    return tuple(
        document
        for document in documents
        if document.permission_key in principal.permissions and document.provenance
    )


def validate_inbound_payload(
    contract: IntegrationContract,
    payload: Mapping[str, object],
) -> tuple[bool, tuple[str, ...]]:
    required = tuple(
        str(value) for value in contract.validation_policy.get("required_fields", ())
    )
    allowed = contract.validation_policy.get("allowed_fields")
    errors: list[str] = []

    for key in required:
        if key not in payload or payload[key] in (None, ""):
            errors.append(f"{key}:required")

    if isinstance(allowed, (list, tuple)):
        allowed_keys = {str(value) for value in allowed}
        extras = sorted(set(payload) - allowed_keys)
        errors.extend(f"{key}:unexpected" for key in extras)

    if "tenant_id" in payload:
        errors.append("tenant_id:payload_authority_forbidden")

    return not errors, tuple(errors)
