from __future__ import annotations

from pydantic import ConfigDict, Field

from app.modules.planogram.schemas import PlanogramPreviewRequest


class PlanogramPhysicalLayoutCandidatePreviewRequest(PlanogramPreviewRequest):
    """Replay one server-generated V5 candidate by fingerprint only."""

    model_config = ConfigDict(extra="forbid")

    layout_fingerprint: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
