from app.modules.audit.authorization import AuditScope, scope_allows_location


def test_unrestricted_scope_allows_any_location() -> None:
    scope = AuditScope(
        unrestricted=True,
        regions=frozenset(),
        location_ids=frozenset(),
    )

    assert scope_allows_location(scope, location_id="store-999", region="TR-MARMARA")


def test_location_scope_allows_only_explicit_location() -> None:
    scope = AuditScope(
        unrestricted=False,
        regions=frozenset(),
        location_ids=frozenset({"store-001"}),
    )

    assert scope_allows_location(scope, location_id="store-001", region="TR-MARMARA")
    assert not scope_allows_location(scope, location_id="store-002", region="TR-MARMARA")


def test_region_scope_allows_location_in_region_only() -> None:
    scope = AuditScope(
        unrestricted=False,
        regions=frozenset({"TR-MARMARA"}),
        location_ids=frozenset(),
    )

    assert scope_allows_location(scope, location_id="store-001", region="TR-MARMARA")
    assert not scope_allows_location(scope, location_id="store-002", region="TR-AEGEAN")


def test_empty_scope_fails_closed() -> None:
    scope = AuditScope(
        unrestricted=False,
        regions=frozenset(),
        location_ids=frozenset(),
    )

    assert not scope_allows_location(scope, location_id="store-001", region=None)
