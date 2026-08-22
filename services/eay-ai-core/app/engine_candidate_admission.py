"""Protocol for runtime engine-candidate admission policies.

The core routing layer intentionally does not own benchmark/certificate storage.
Production composition may inject a policy that can only *remove* candidate
engines. The policy never grants provider spend or side-effect authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .engine_gateway import RegisteredEngine
from .intelligence_router import IntelligenceTask


class EngineCandidateAdmission(Protocol):
    def is_admitted(
        self,
        *,
        task: IntelligenceTask,
        registration: RegisteredEngine,
        requested_at: datetime,
        tenant_ref: str,
        company_ref: str | None,
    ) -> bool: ...

    def receipt_ref(
        self,
        *,
        task: IntelligenceTask,
        requested_at: datetime,
        tenant_ref: str,
        company_ref: str | None,
    ) -> str | None: ...
