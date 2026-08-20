from app.modules.planogram.temporal_realogram import evaluate_temporal_realogram


def baseline_plan():
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": 1,
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "products": [
                                    {
                                        "sku": "COLA",
                                        "facing_count": 3,
                                        "barcode": "8690001",
                                    },
                                    {
                                        "sku": "WATER",
                                        "facing_count": 2,
                                        "barcode": "8690002",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_temporal_realogram_closes_oos_loop_and_flags_physical_delta():
    events = [
        {
            "event_type": "shelf_scan",
            "observed_at": "2026-08-20T10:00:00Z",
            "sku": "COLA",
            "source_ref": "scan://1",
            "aisle_id": "B",
            "module_id": 1,
            "shelf_no": 1,
            "facing_count": 1,
            "confidence": 0.95,
            "image_quality_score": 0.9,
            "occlusion_pct": 5,
        },
        {
            "event_type": "pick_sequence_step",
            "observed_at": "2026-08-20T10:02:00Z",
            "sku": "WATER",
            "source_ref": "route://1",
            "flow_id": "flow-1",
            "sequence_no": 1,
            "aisle_id": "A",
            "module_id": 1,
            "shelf_no": 1,
        },
        {
            "event_type": "barcode_pick",
            "observed_at": "2026-08-20T10:03:00Z",
            "sku": "WATER",
            "source_ref": "scanner://1",
            "flow_id": "flow-1",
            "barcode": "8690002",
        },
        {
            "event_type": "inventory_oos",
            "observed_at": "2026-08-20T10:05:00Z",
            "sku": "WATER",
            "source_ref": "inventory://1",
            "flow_id": "flow-1",
        },
        {
            "event_type": "substitution",
            "observed_at": "2026-08-20T10:06:00Z",
            "sku": "WATER",
            "substitute_sku": "COLA",
            "source_ref": "pick://sub-1",
            "flow_id": "flow-1",
        },
        {
            "event_type": "replenishment",
            "observed_at": "2026-08-20T10:35:00Z",
            "sku": "WATER",
            "source_ref": "replen://1",
            "flow_id": "flow-1",
        },
        {
            "event_type": "cold_chain_transition",
            "observed_at": "2026-08-20T10:36:00Z",
            "sku": "WATER",
            "source_ref": "cold://1",
            "flow_id": "flow-1",
            "elapsed_seconds": 900,
            "allowed_seconds": 600,
        },
    ]
    result = evaluate_temporal_realogram(
        plan_payload=baseline_plan(),
        events=events,
        as_of="2026-08-20T10:40:00Z",
    )
    codes = {row["alert_code"] for row in result["alerts"]}
    assert "sku_misplaced" in codes
    assert "confirmed_oos" in codes
    assert "cold_chain_transition_breach" in codes
    assert result["closed_loop"]["confirmed_oos_count"] == 1
    assert result["closed_loop"]["pick_sequence_step_event_count"] == 1
    assert result["closed_loop"]["barcode_pick_event_count"] == 1
    assert result["closed_loop"]["open_oos_count"] == 0
    water = next(
        row for row in result["sku_summaries"] if row["sku"] == "WATER"
    )
    assert water["mean_replenishment_latency_minutes"] == 30.0


def test_low_confidence_scan_goes_to_review_not_truth():
    result = evaluate_temporal_realogram(
        plan_payload=baseline_plan(),
        events=[
            {
                "event_type": "shelf_scan",
                "observed_at": "2026-08-20T10:00:00Z",
                "sku": "COLA",
                "source_ref": "scan://weak",
                "aisle_id": "B",
                "module_id": 1,
                "shelf_no": 1,
                "facing_count": 1,
                "confidence": 0.55,
                "image_quality_score": 0.9,
                "occlusion_pct": 5,
            }
        ],
    )
    assert result["review_required_count"] == 1
    assert not any(
        row.get("alert_code") == "sku_misplaced"
        for row in result["alerts"]
    )
    assert result["field_truth"] is False


def test_stale_state_is_deterministic_from_as_of():
    result = evaluate_temporal_realogram(
        plan_payload=baseline_plan(),
        events=[
            {
                "event_type": "shelf_scan",
                "observed_at": "2026-08-20T10:00:00Z",
                "sku": "COLA",
                "source_ref": "scan://1",
                "aisle_id": "A",
                "module_id": 1,
                "shelf_no": 1,
                "facing_count": 3,
                "confidence": 0.95,
                "image_quality_score": 0.9,
                "occlusion_pct": 5,
            }
        ],
        as_of="2026-08-20T15:00:00Z",
        stale_after_minutes=240,
    )
    assert any(
        row.get("alert_code") == "realogram_state_stale"
        for row in result["alerts"]
    )
    assert result["latest_realogram"][0]["usable"] is True
