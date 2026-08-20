from app.modules.planogram.realogram_v2 import evaluate_temporal_realogram_v2


def _plan():
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "1",
                        "shelves": [
                            {
                                "shelf_no": "1",
                                "products": [
                                    {"sku": "SKU-1", "facing_count": 2, "barcode": "123"}
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_multisource_realogram_deduplicates_and_closes_replenished_oos():
    events = [
        {
            "provider": "wms",
            "provider_event_id": "oos-1",
            "event_type": "inventory_oos",
            "observed_at": "2026-08-20T10:00:00Z",
            "sku": "SKU-1",
            "source_ref": "wms://event/oos-1",
        },
        {
            "provider": "wms",
            "provider_event_id": "oos-1",
            "event_type": "inventory_oos",
            "observed_at": "2026-08-20T10:00:00Z",
            "sku": "SKU-1",
            "source_ref": "wms://event/oos-1",
        },
        {
            "provider": "scanner",
            "provider_event_id": "rep-1",
            "event_type": "replenishment",
            "observed_at": "2026-08-20T10:15:00Z",
            "sku": "SKU-1",
            "source_ref": "scanner://event/rep-1",
        },
    ]
    result = evaluate_temporal_realogram_v2(plan_payload=_plan(), events=events)
    assert result["available"] is True
    assert result["duplicate_event_count"] == 1
    assert result["open_action_count"] == 0
    assert result["resolved_action_count"] == 1
    assert result["resolved_actions"][0]["resolution"] == (
        "replenishment_observed_after_oos"
    )
    assert result["server_connector_provenance_verified"] is False
    assert result["auto_execute_allowed"] is False


def test_action_identity_is_stable_and_duplicate_alerts_are_deduplicated():
    events = [
        {
            "provider": "shelf_cv",
            "provider_event_id": "scan-1",
            "event_type": "shelf_scan",
            "observed_at": "2026-08-20T10:00:00Z",
            "sku": "SKU-1",
            "source_ref": "cv://scan/1",
            "aisle_id": "A",
            "module_id": "1",
            "shelf_no": "1",
            "facing_count": 1,
            "confidence": 0.99,
            "image_quality_score": 0.99,
            "occlusion_pct": 0,
        }
    ]
    first = evaluate_temporal_realogram_v2(plan_payload=_plan(), events=events)
    second = evaluate_temporal_realogram_v2(plan_payload=_plan(), events=events)
    assert first["open_action_count"] == 1
    assert first["action_queue"][0]["action_id"] == second["action_queue"][0]["action_id"]
    assert first["action_state_contract"] == "stable-id-dedup-open-resolved-v1"


def test_provider_label_alone_cannot_be_field_truth():
    result = evaluate_temporal_realogram_v2(
        plan_payload=_plan(),
        events=[
            {
                "provider": "iot_shelf",
                "provider_event_id": "scan-1",
                "event_type": "shelf_scan",
                "observed_at": "2026-08-20T10:00:00Z",
                "sku": "SKU-1",
                "source_ref": "iot://scan/1",
                "aisle_id": "A",
                "module_id": "1",
                "shelf_no": "1",
                "facing_count": 2,
                "confidence": 0.99,
                "image_quality_score": 0.99,
                "occlusion_pct": 0,
            }
        ],
    )
    assert result["provenance_fields_complete"] is True
    assert result["server_connector_provenance_verified"] is False
    assert result["field_truth"] is False
