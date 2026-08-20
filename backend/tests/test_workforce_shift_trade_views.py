from __future__ import annotations

from app.modules.workforce import service, shift_trade_views, shift_trading


def _shift(shift_id: str, person_id: str, warehouse_id: str = "W1") -> dict:
    return {
        "id": shift_id,
        "person_id": person_id,
        "person_name": person_id,
        "status": "Atandı",
        "warehouse_id": warehouse_id,
        "warehouse": f"Warehouse {warehouse_id}",
        "date": "2099-01-10",
        "start": "09:00",
        "end": "17:00",
        "role": "Worker",
    }


def _prepare_candidate_authority(monkeypatch, trades=None, evaluator=None) -> None:
    monkeypatch.setattr(shift_trading, "_hydrate_schedule", lambda: None)
    monkeypatch.setattr(shift_trading, "_load_trades", lambda: list(trades or []))
    monkeypatch.setattr(shift_trading, "_assert_shift_tradeable", lambda shift, owner: None)
    monkeypatch.setattr(
        shift_trading,
        "_evaluate_assignment",
        evaluator or (lambda shift, person_id, ignored_shift_ids=None: {
            "eligible": True,
            "reasons": [],
            "preference_match": person_id == "P1",
        }),
    )
    monkeypatch.setattr(
        service,
        "resolve_person_identity",
        lambda person_id, identity_type: {
            "employee_id": person_id,
            "full_name": {"P1": "Requester", "P2": "Coworker"}.get(person_id, person_id),
        },
    )


def test_swap_candidates_are_two_way_eligible_and_do_not_expose_employee_ids(monkeypatch):
    monkeypatch.setattr(service, "_SHIFTS", [_shift("S1", "P1"), _shift("S2", "P2")])
    _prepare_candidate_authority(monkeypatch)

    rows = shift_trade_views.list_swap_candidates("P1", "S1")

    assert len(rows) == 1
    assert rows[0]["shift_id"] == "S2"
    assert rows[0]["counterpart_display_name"] == "Coworker"
    assert "person_id" not in rows[0]
    assert "target_person_id" not in rows[0]
    assert "employee_id" not in rows[0]


def test_swap_candidate_is_excluded_when_either_direction_is_ineligible(monkeypatch):
    monkeypatch.setattr(service, "_SHIFTS", [_shift("S1", "P1"), _shift("S2", "P2")])

    def evaluator(shift, person_id, ignored_shift_ids=None):
        return {
            "eligible": not (str(shift["id"]) == "S2" and person_id == "P1"),
            "reasons": ["REST_RULE"] if str(shift["id"]) == "S2" and person_id == "P1" else [],
            "preference_match": False,
        }

    _prepare_candidate_authority(monkeypatch, evaluator=evaluator)

    assert shift_trade_views.list_swap_candidates("P1", "S1") == []


def test_swap_candidate_is_locked_when_target_shift_is_already_part_of_active_trade(monkeypatch):
    monkeypatch.setattr(service, "_SHIFTS", [_shift("S1", "P1"), _shift("S2", "P2")])
    _prepare_candidate_authority(
        monkeypatch,
        trades=[{
            "id": "TRADE-OTHER",
            "status": "PENDING_EMPLOYEE_ACCEPTANCE",
            "shift_id": "S9",
            "target_shift_id": "S2",
        }],
    )

    assert shift_trade_views.list_swap_candidates("P1", "S1") == []


def test_manager_trade_view_is_worksite_scoped_and_active_only(monkeypatch):
    monkeypatch.setattr(
        service,
        "_SHIFTS",
        [
            _shift("S1", "P1", "W1"),
            _shift("S2", "P2", "W1"),
            _shift("S3", "P3", "W2"),
        ],
    )
    monkeypatch.setattr(shift_trading, "_hydrate_schedule", lambda: None)
    monkeypatch.setattr(
        shift_trading,
        "_load_trades",
        lambda: [
            {
                "id": "TRADE-ACTIVE",
                "status": "PENDING_MANAGER_APPROVAL",
                "mode": "SWAP",
                "warehouse_id": "W1",
                "date": "2099-01-10",
                "created_at": "2099-01-01T10:00:00Z",
                "shift_id": "S1",
                "target_shift_id": "S2",
                "requester_person_id": "P1",
                "target_person_id": "P2",
            },
            {
                "id": "TRADE-FINAL",
                "status": "APPROVED",
                "mode": "TRANSFER",
                "warehouse_id": "W1",
                "date": "2099-01-10",
                "created_at": "2099-01-01T09:00:00Z",
                "shift_id": "S1",
                "requester_person_id": "P1",
                "target_person_id": "P2",
            },
            {
                "id": "TRADE-OTHER-WORKSITE",
                "status": "PENDING_MANAGER_APPROVAL",
                "mode": "TRANSFER",
                "warehouse_id": "W2",
                "date": "2099-01-10",
                "created_at": "2099-01-01T08:00:00Z",
                "shift_id": "S3",
                "requester_person_id": "P3",
                "target_person_id": "P2",
            },
        ],
    )
    monkeypatch.setattr(
        service,
        "resolve_person_identity",
        lambda person_id, identity_type: {"full_name": f"Name {person_id}"},
    )

    rows = shift_trade_views.list_manager_shift_trades("W1", active_only=True)

    assert [row["id"] for row in rows] == ["TRADE-ACTIVE"]
    assert rows[0]["requester_display_name"] == "Name P1"
    assert rows[0]["target_display_name"] == "Name P2"
    assert rows[0]["source_shift"]["shift_id"] == "S1"
    assert rows[0]["target_shift"]["shift_id"] == "S2"

    history = shift_trade_views.list_manager_shift_trades("W1", active_only=False)
    assert {row["id"] for row in history} == {"TRADE-ACTIVE", "TRADE-FINAL"}
