from __future__ import annotations

from contextlib import contextmanager

import pytest

from backend.app.modules.workforce import active_shift


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class _Database:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


@contextmanager
def _connection(rows):
    yield _Database(rows)


def _install(monkeypatch: pytest.MonkeyPatch, rows):
    monkeypatch.setattr(active_shift.persistence, "ENABLED", True)
    monkeypatch.setattr(active_shift.persistence, "tenant_id", lambda: "tenant-1")
    monkeypatch.setattr(active_shift.persistence, "connection", lambda: _connection(rows))


def test_active_shift_requires_same_tenant_employee_and_warehouse(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [("ATT-1", "SHIFT-1", "E-1", "2026-08-18T15:00:00+00:00", "FULYA")],
    )

    attestation = active_shift.resolve_active_shift(
        "tenant-1",
        "E-1",
        frozenset({"fulya", "USKUDAR"}),
    )

    assert attestation is not None
    assert attestation.shift_id == "SHIFT-1"
    assert attestation.attendance_id == "ATT-1"
    assert attestation.employee_id == "E-1"
    assert attestation.warehouse_id == "FULYA"
    assert attestation.tenant_id == "tenant-1"


def test_no_open_shift_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, [])
    assert active_shift.resolve_active_shift("tenant-1", "E-1", {"FULYA"}) is None


def test_tenant_mismatch_fails_closed_before_database_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(active_shift.persistence, "tenant_id", lambda: "tenant-1")
    monkeypatch.setattr(active_shift.persistence, "ENABLED", True)

    with pytest.raises(PermissionError, match="tenant"):
        active_shift.resolve_active_shift("tenant-2", "E-1", {"FULYA"})


def test_missing_postgres_authority_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(active_shift.persistence, "tenant_id", lambda: "tenant-1")
    monkeypatch.setattr(active_shift.persistence, "ENABLED", False)

    with pytest.raises(active_shift.ActiveShiftAuthorityError, match="PostgreSQL"):
        active_shift.resolve_active_shift("tenant-1", "E-1", {"FULYA"})


def test_multiple_open_shifts_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [
            ("ATT-1", "SHIFT-1", "E-1", "2026-08-18T15:00:00+00:00", "FULYA"),
            ("ATT-2", "SHIFT-2", "E-1", "2026-08-18T16:00:00+00:00", "FULYA"),
        ],
    )

    with pytest.raises(active_shift.ActiveShiftAuthorityError, match="birden fazla"):
        active_shift.resolve_active_shift("tenant-1", "E-1", {"FULYA"})


def test_empty_warehouse_scope_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(active_shift.persistence, "tenant_id", lambda: "tenant-1")
    monkeypatch.setattr(active_shift.persistence, "ENABLED", True)

    with pytest.raises(PermissionError, match="depo kapsamı"):
        active_shift.resolve_active_shift("tenant-1", "E-1", set())


def test_offline_event_is_valid_inside_completed_shift_window(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [(
            "ATT-1",
            "SHIFT-1",
            "E-1",
            "2026-08-18T15:00:00+00:00",
            "2026-08-18T16:00:00+00:00",
            "FULYA",
            "Tamamlandı",
        )],
    )

    attestation = active_shift.attest_shift_at_event(
        "tenant-1",
        "E-1",
        "FULYA",
        "SHIFT-1",
        "2026-08-18T15:30:00+00:00",
    )

    assert attestation is not None
    assert attestation.shift_id == "SHIFT-1"
    assert attestation.attendance_id == "ATT-1"


def test_offline_event_before_checkin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [(
            "ATT-1",
            "SHIFT-1",
            "E-1",
            "2026-08-18T15:00:00+00:00",
            "2026-08-18T16:00:00+00:00",
            "FULYA",
            "Tamamlandı",
        )],
    )
    assert active_shift.attest_shift_at_event(
        "tenant-1", "E-1", "FULYA", "SHIFT-1", "2026-08-18T14:59:59+00:00"
    ) is None


def test_offline_event_after_checkout_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [(
            "ATT-1",
            "SHIFT-1",
            "E-1",
            "2026-08-18T15:00:00+00:00",
            "2026-08-18T16:00:00+00:00",
            "FULYA",
            "Tamamlandı",
        )],
    )
    assert active_shift.attest_shift_at_event(
        "tenant-1", "E-1", "FULYA", "SHIFT-1", "2026-08-18T16:00:01+00:00"
    ) is None


def test_open_shift_allows_event_after_checkin(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [(
            "ATT-1",
            "SHIFT-1",
            "E-1",
            "2026-08-18T15:00:00+00:00",
            None,
            "FULYA",
            "Vardiyada",
        )],
    )
    assert active_shift.attest_shift_at_event(
        "tenant-1", "E-1", "FULYA", "SHIFT-1", "2026-08-18T15:30:00+00:00"
    ) is not None


def test_future_event_time_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [(
            "ATT-1",
            "SHIFT-1",
            "E-1",
            "2026-08-18T15:00:00+00:00",
            None,
            "FULYA",
            "Vardiyada",
        )],
    )
    with pytest.raises(PermissionError, match="gelecekte"):
        active_shift.attest_shift_at_event(
            "tenant-1", "E-1", "FULYA", "SHIFT-1", "2099-01-01T00:00:00+00:00"
        )
