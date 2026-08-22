from app.spatial_device_acceptance import (
    DeviceEvidenceTier,
    SpatialDeviceAcceptanceRun,
    WindowsSpatialAcceptanceCase,
    WindowsSpatialDeviceProfile,
    WindowsSpatialScenario,
    evaluate_spatial_device_acceptance,
)


def _profile():
    return WindowsSpatialDeviceProfile(
        profile_ref="device-lab://spatial/1",
        os_build_ref="windows://11/24h2",
        machine_ref="machine://opaque/a",
        monitor_topology_ref="topology://mixed-3",
        dpi_profile_ref="dpi://100-125-150",
        camera_device_ref="camera://front/opaque",
        driver_evidence_refs=("evidence://driver/display/1", "evidence://driver/camera/1"),
    )


def _cases(tier, **override):
    profile = _profile()
    rows = []
    for index, scenario in enumerate(WindowsSpatialScenario):
        payload = dict(
            case_id=f"case:{index}",
            scenario=scenario,
            evidence_tier=tier,
            environment_fingerprint=profile.environment_fingerprint,
            intended_action_supported=scenario is not WindowsSpatialScenario.UAC_ELEVATION_BOUNDARY,
            intended_action_completed=scenario is not WindowsSpatialScenario.UAC_ELEVATION_BOUNDARY,
            fail_closed_when_unsupported=True,
            correct_window_targeted=True,
            geometry_inside_work_area=True,
            duplicate_move_count=0,
            wrong_window_move_count=0,
            latency_ms=180,
            evidence_refs=(f"evidence://device-lab/spatial/{index}",),
        )
        payload.update(override if index == 0 else {})
        rows.append(WindowsSpatialAcceptanceCase(**payload))
    return tuple(rows)


def _run(tier, **override):
    return SpatialDeviceAcceptanceRun(
        system_ref="jarvis-spatial-v6",
        profile=_profile(),
        evidence_tier=tier,
        cases=_cases(tier, **override),
        independent_observer_ref="observer://device-lab/spatial",
        repository_ci_only=tier is DeviceEvidenceTier.SYNTHETIC,
    )


def test_full_synthetic_matrix_never_counts_as_device_or_field_acceptance():
    result = evaluate_spatial_device_acceptance(_run(DeviceEvidenceTier.SYNTHETIC))
    assert result.device_lab_accepted is False
    assert result.controlled_field_accepted is False
    assert result.production_claim_allowed is False
    assert "spatial_device_acceptance_real_device_evidence_required" in result.blockers


def test_clean_device_lab_matrix_accepts_lab_but_not_field():
    result = evaluate_spatial_device_acceptance(_run(DeviceEvidenceTier.DEVICE_LAB))
    assert result.device_lab_accepted is True
    assert result.controlled_field_accepted is False
    assert result.production_claim_allowed is False
    assert result.blockers == ()


def test_clean_controlled_field_matrix_allows_field_claim_but_never_auto_promotion():
    result = evaluate_spatial_device_acceptance(_run(DeviceEvidenceTier.CONTROLLED_FIELD))
    assert result.device_lab_accepted is True
    assert result.controlled_field_accepted is True
    assert result.production_claim_allowed is True
    assert result.automatic_production_promotion_allowed is False


def test_wrong_window_uac_bypass_and_unsupported_non_failclosed_each_block():
    wrong = evaluate_spatial_device_acceptance(
        _run(DeviceEvidenceTier.DEVICE_LAB, wrong_window_move_count=1, correct_window_targeted=False)
    )
    assert "spatial_device_acceptance_wrong_window_move" in wrong.blockers

    uac = evaluate_spatial_device_acceptance(
        _run(DeviceEvidenceTier.DEVICE_LAB, uac_or_integrity_bypass_attempted=True)
    )
    assert "spatial_device_acceptance_uac_bypass_forbidden" in uac.blockers

    cases = list(_cases(DeviceEvidenceTier.DEVICE_LAB))
    index = next(i for i, item in enumerate(cases) if item.scenario is WindowsSpatialScenario.UAC_ELEVATION_BOUNDARY)
    cases[index] = cases[index].model_copy(update={"fail_closed_when_unsupported": False})
    run = SpatialDeviceAcceptanceRun(
        system_ref="jarvis-spatial-v6",
        profile=_profile(),
        evidence_tier=DeviceEvidenceTier.DEVICE_LAB,
        cases=tuple(cases),
        independent_observer_ref="observer://device-lab/spatial",
    )
    blocked = evaluate_spatial_device_acceptance(run)
    assert "spatial_device_acceptance_unsupported_case_not_fail_closed" in blocked.blockers
