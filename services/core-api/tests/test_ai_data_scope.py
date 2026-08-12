from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.ai_data_scope import (
    AiDataScope,
    AiDataScopeEmpty,
    AiDataScopeInvalid,
    ai_data_scope_fingerprint,
    intersect_ai_data_scopes,
    parse_ai_data_scope,
    union_ai_data_scopes,
    validate_ai_data_scope_invocation,
)


def raw_scope(*stores: str) -> dict[str, object]:
    return {
        "ai_data_scope": {
            "version": 1,
            "store_names": list(stores),
        }
    }


def test_scope_normalizes_unicode_whitespace_and_order() -> None:
    scope = parse_ai_data_scope(
        raw_scope(
            "  Fulya  ",
            "İçerenköy",
            "Anka",
        )
    )

    assert scope == AiDataScope(
        version=1,
        store_names=(
            "Anka",
            "Fulya",
            "İçerenköy",
        ),
    )


def test_model_revalidates_stored_scope_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AiDataScope.model_validate(
            {
                "version": 1,
                "store_names": ["*"],
            }
        )

    with pytest.raises(ValidationError):
        AiDataScope.model_validate(
            {
                "version": 1,
                "store_names": ["Fulya"],
                "all_stores": True,
            }
        )

    with pytest.raises(ValidationError):
        AiDataScope.model_validate(
            {
                "store_names": ["Fulya"],
            }
        )


def test_empty_unversioned_unknown_and_wildcard_scope_fail_closed() -> None:
    invalid = (
        {},
        {"stores": ["Fulya"]},
        {"ai_data_scope": {"store_names": ["Fulya"]}},
        {
            "ai_data_scope": {
                "version": 2,
                "store_names": ["Fulya"],
            }
        },
        {
            "ai_data_scope": {
                "version": 1,
                "store_names": ["*"],
            }
        },
        {
            "ai_data_scope": {
                "version": 1,
                "store_names": ["Ful%"],
            }
        },
        {
            "ai_data_scope": {
                "version": 1,
                "store_names": [],
            }
        },
    )

    for value in invalid:
        with pytest.raises(
            (AiDataScopeInvalid, AiDataScopeEmpty)
        ):
            parse_ai_data_scope(value)


def test_duplicate_store_names_after_normalization_are_rejected() -> None:
    with pytest.raises(AiDataScopeInvalid):
        parse_ai_data_scope(
            raw_scope(
                "Fulya",
                " fulya ",
            )
        )


def test_same_permission_role_scopes_union_without_widening_sentinel() -> None:
    combined = union_ai_data_scopes(
        (
            parse_ai_data_scope(
                raw_scope("Fulya", "Anka")
            ),
            parse_ai_data_scope(
                raw_scope("Dicle")
            ),
        )
    )

    assert combined.store_names == (
        "Anka",
        "Dicle",
        "Fulya",
    )


def test_independently_required_permissions_intersect() -> None:
    effective = intersect_ai_data_scopes(
        (
            parse_ai_data_scope(
                raw_scope("Fulya", "Anka")
            ),
            parse_ai_data_scope(
                raw_scope("Fulya", "Dicle")
            ),
        )
    )

    assert effective.store_names == ("Fulya",)


def test_nonoverlapping_required_permissions_fail_closed() -> None:
    with pytest.raises(AiDataScopeEmpty):
        intersect_ai_data_scopes(
            (
                parse_ai_data_scope(
                    raw_scope("Fulya")
                ),
                parse_ai_data_scope(
                    raw_scope("Dicle")
                ),
            )
        )


def test_ops_invocation_requires_explicit_canonical_store_subset() -> None:
    scope = parse_ai_data_scope(
        raw_scope("Anka", "Fulya")
    )

    accepted = validate_ai_data_scope_invocation(
        tool="ops_kpi_query",
        arguments={
            "metric": "orders",
            "stores": ["Anka", "Fulya"],
        },
        data_scope=scope,
    )
    assert accepted == ("Anka", "Fulya")

    for arguments in (
        {"metric": "orders"},
        {"metric": "orders", "stores": []},
        {"metric": "orders", "stores": ["Dicle"]},
        {"metric": "orders", "stores": [" fulya "]},
        {"metric": "orders", "stores": ["fulya"]},
    ):
        with pytest.raises(AiDataScopeInvalid):
            validate_ai_data_scope_invocation(
                tool="ops_kpi_query",
                arguments=arguments,
                data_scope=scope,
            )


def test_tools_without_reviewed_data_scope_adapter_fail_closed() -> None:
    scope = parse_ai_data_scope(
        raw_scope("Fulya")
    )

    for tool in (
        "catalog_query",
        "regulatory_impact_query",
    ):
        with pytest.raises(AiDataScopeInvalid):
            validate_ai_data_scope_invocation(
                tool=tool,
                arguments={},
                data_scope=scope,
            )


def test_data_scope_fingerprint_is_stable_and_scope_sensitive() -> None:
    first = parse_ai_data_scope(
        raw_scope("Fulya", "Anka")
    )
    reordered = parse_ai_data_scope(
        raw_scope("Anka", "Fulya")
    )
    changed = parse_ai_data_scope(
        raw_scope("Anka")
    )

    assert ai_data_scope_fingerprint(first) == (
        ai_data_scope_fingerprint(reordered)
    )
    assert ai_data_scope_fingerprint(first) != (
        ai_data_scope_fingerprint(changed)
    )

    fingerprint = ai_data_scope_fingerprint(first)
    assert len(fingerprint) == 64
    int(fingerprint, 16)
