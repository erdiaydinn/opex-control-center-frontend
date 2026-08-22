from datetime import datetime, timedelta, timezone

import pytest

from app.desktop_window_runtime import DesktopRect, MonitorGeometry
from app.workspace_choreography import WorkspaceProfile, WorkspaceRole, WorkspaceSlot
from app.workspace_profile_memory import (
    WorkspaceApproval,
    monitor_topology_fingerprint,
    resolve_workspace_memory,
    store_workspace_profile,
)

NOW = datetime(2026, 8, 18, 12, 10, tzinfo=timezone.utc)


def _monitors(*, shifted=False):
    offset = 100 if shifted else 0
    return (
        MonitorGeometry(
            monitor_id="monitor:left",
            bounds=DesktopRect(left=-1920 + offset, top=0, right=0 + offset, bottom=1080),
            work_area=DesktopRect(left=-1920 + offset, top=0, right=0 + offset, bottom=1040),
        ),
        MonitorGeometry(
            monitor_id="monitor:main",
            bounds=DesktopRect(left=0 + offset, top=0, right=1920 + offset, bottom=1080),
            work_area=DesktopRect(left=0 + offset, top=0, right=1920 + offset, bottom=1040),
            primary=True,
        ),
    )


def _profile():
    return WorkspaceProfile(
        profile_ref="workspace:planogram-mastery",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        slots=(
            WorkspaceSlot(role=WorkspaceRole.PLANOGRAM_2D, monitor_id="monitor:left", left=0, top=0, right=1, bottom=1),
            WorkspaceSlot(role=WorkspaceRole.PLANOGRAM_3D, monitor_id="monitor:main", left=0, top=0, right=1, bottom=1),
        ),
    )


def _approval(**updates):
    payload = dict(
        approval_ref="approval://workspace/1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        approved_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=90),
        purpose="remember_workspace_layout",
    )
    payload.update(updates)
    return WorkspaceApproval(**payload)


def test_explicit_approval_can_store_metadata_only_workspace_memory():
    memory = store_workspace_profile(
        profile=_profile(),
        approval=_approval(),
        monitors=_monitors(),
        stored_at=NOW,
        profile_version=1,
    )
    assert memory.topology_fingerprint == monitor_topology_fingerprint(_monitors())
    assert memory.application_content_retained is False
    assert memory.window_titles_retained is False
    assert memory.business_side_effects_authorized is False

    resolved = resolve_workspace_memory(
        memory=memory,
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        monitors=_monitors(),
        now=NOW,
    )
    assert resolved.profile is not None
    assert resolved.automatic_execution_authorized is False


def test_observation_only_auto_persistence_is_forbidden():
    with pytest.raises(ValueError, match="cannot_learn_from_observation_without_approval"):
        _approval(automatic_observation_persistence_allowed=True)


def test_topology_change_or_identity_change_blocks_memory_reuse():
    memory = store_workspace_profile(
        profile=_profile(),
        approval=_approval(),
        monitors=_monitors(),
        stored_at=NOW,
        profile_version=1,
    )
    drift = resolve_workspace_memory(
        memory=memory,
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        monitors=_monitors(shifted=True),
        now=NOW,
    )
    assert drift.profile is None
    assert "workspace_memory_topology_changed" in drift.blockers

    wrong_identity = resolve_workspace_memory(
        memory=memory,
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://other",
        monitors=_monitors(),
        now=NOW,
    )
    assert "workspace_memory_identity_mismatch" in wrong_identity.blockers


def test_profile_cannot_remember_unobserved_monitor():
    profile = _profile().model_copy(
        update={
            "slots": (
                WorkspaceSlot(role=WorkspaceRole.KPI, monitor_id="monitor:ghost", left=0, top=0, right=1, bottom=1),
            )
        }
    )
    with pytest.raises(ValueError, match="profile_monitor_not_observed"):
        store_workspace_profile(
            profile=profile,
            approval=_approval(),
            monitors=_monitors(),
            stored_at=NOW,
            profile_version=1,
        )
