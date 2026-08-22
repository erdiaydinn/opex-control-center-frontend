from app.desktop_window_runtime import DesktopRect, MonitorGeometry, WindowGeometry
from app.workspace_choreography import (
    WorkspaceProfile,
    WorkspaceRole,
    WorkspaceSlot,
    WorkspaceWindowBinding,
    execute_workspace,
    plan_workspace,
)


class _Backend:
    def __init__(self):
        self.moves = []

    def move_window(self, window_ref, rect, *, restore_maximized):
        self.moves.append((window_ref, rect, restore_maximized))


def _monitors():
    return (
        MonitorGeometry(
            monitor_id="monitor:left",
            bounds=DesktopRect(left=-1920, top=0, right=0, bottom=1080),
            work_area=DesktopRect(left=-1920, top=0, right=0, bottom=1040),
        ),
        MonitorGeometry(
            monitor_id="monitor:center",
            bounds=DesktopRect(left=0, top=0, right=1920, bottom=1080),
            work_area=DesktopRect(left=0, top=0, right=1920, bottom=1040),
            primary=True,
        ),
        MonitorGeometry(
            monitor_id="monitor:right",
            bounds=DesktopRect(left=1920, top=0, right=3840, bottom=1080),
            work_area=DesktopRect(left=1920, top=0, right=3840, bottom=1040),
        ),
    )


def _windows():
    return (
        WindowGeometry(window_ref="window:2d", rect=DesktopRect(left=20, top=20, right=900, bottom=700)),
        WindowGeometry(window_ref="window:3d", rect=DesktopRect(left=100, top=100, right=1000, bottom=800)),
        WindowGeometry(window_ref="window:kpi", rect=DesktopRect(left=300, top=120, right=1100, bottom=720)),
    )


def _profile():
    return WorkspaceProfile(
        profile_ref="workspace:planogram-mastery",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        slots=(
            WorkspaceSlot(role=WorkspaceRole.PLANOGRAM_2D, monitor_id="monitor:left", left=0, top=0, right=1, bottom=1),
            WorkspaceSlot(role=WorkspaceRole.PLANOGRAM_3D, monitor_id="monitor:center", left=0, top=0, right=1, bottom=1),
            WorkspaceSlot(role=WorkspaceRole.KPI, monitor_id="monitor:right", left=0, top=0, right=1, bottom=1),
        ),
    )


def test_planogram_workspace_choreography_handles_negative_monitor_coordinates():
    bindings = (
        WorkspaceWindowBinding(role=WorkspaceRole.PLANOGRAM_2D, window_ref="window:2d"),
        WorkspaceWindowBinding(role=WorkspaceRole.PLANOGRAM_3D, window_ref="window:3d"),
        WorkspaceWindowBinding(role=WorkspaceRole.KPI, window_ref="window:kpi"),
    )
    plan = plan_workspace(profile=_profile(), bindings=bindings, windows=_windows(), monitors=_monitors())
    assert plan.blockers == ()
    assert plan.moves[0].after_rect.left == -1920
    assert plan.moves[1].after_rect.left == 0
    assert plan.moves[2].after_rect.left == 1920
    assert plan.business_side_effects_authorized is False

    backend = _Backend()
    receipt = execute_workspace(plan=plan, backend=backend)
    assert receipt.completed is True
    assert len(backend.moves) == 3
    assert receipt.business_side_effects_authorized is False


def test_missing_exact_window_blocks_entire_workspace_plan():
    bindings = (
        WorkspaceWindowBinding(role=WorkspaceRole.PLANOGRAM_2D, window_ref="window:missing"),
        WorkspaceWindowBinding(role=WorkspaceRole.PLANOGRAM_3D, window_ref="window:3d"),
    )
    plan = plan_workspace(profile=_profile(), bindings=bindings, windows=_windows(), monitors=_monitors())
    assert plan.moves == ()
    assert any("window_missing" in blocker for blocker in plan.blockers)


def test_duplicate_window_binding_is_rejected_without_partial_movement():
    bindings = (
        WorkspaceWindowBinding(role=WorkspaceRole.PLANOGRAM_2D, window_ref="window:2d"),
        WorkspaceWindowBinding(role=WorkspaceRole.PLANOGRAM_3D, window_ref="window:2d"),
    )
    plan = plan_workspace(profile=_profile(), bindings=bindings, windows=_windows(), monitors=_monitors())
    assert plan.moves == ()
    assert "workspace_choreography_duplicate_window_binding" in plan.blockers
