from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from .jarvis_core_bridge import (
    JarvisCoreBridgeConfigurationError,
    TrustedCoreExecutionContext,
)

Environment = Literal["development", "test", "staging", "production"]


class JarvisTenantPolicyError(PermissionError):
    """The trusted Core execution context is outside this AI instance scope."""


@dataclass(frozen=True)
class JarvisTenantExecutionPolicy:
    environment: Environment
    tenant_id: UUID | None

    @classmethod
    def from_environment(cls) -> "JarvisTenantExecutionPolicy":
        environment_raw = os.getenv("EAY_AI_ENVIRONMENT", "development").strip().lower()
        if environment_raw not in {"development", "test", "staging", "production"}:
            raise JarvisCoreBridgeConfigurationError("EAY_AI_ENVIRONMENT is invalid")

        tenant_raw = os.getenv("EAY_JARVIS_TENANT_ID", "").strip()
        tenant_id: UUID | None = None
        if tenant_raw:
            try:
                tenant_id = UUID(tenant_raw)
            except ValueError as exc:
                raise JarvisCoreBridgeConfigurationError(
                    "EAY_JARVIS_TENANT_ID must be a UUID"
                ) from exc

        policy = cls(
            environment=environment_raw,  # type: ignore[arg-type]
            tenant_id=tenant_id,
        )
        policy.validate()
        return policy

    @property
    def production_like(self) -> bool:
        return self.environment in {"staging", "production"}

    def validate(self) -> None:
        if self.production_like and self.tenant_id is None:
            raise JarvisCoreBridgeConfigurationError(
                "Staging and production Jarvis execution require EAY_JARVIS_TENANT_ID"
            )

    def authorize(self, context: TrustedCoreExecutionContext) -> None:
        self.validate()
        if self.tenant_id is None:
            return
        if context.tenant_id != self.tenant_id:
            raise JarvisTenantPolicyError("jarvis_tenant_mismatch")


def legacy_caller_scope_execution_allowed(
    environment: Environment,
) -> bool:
    """Legacy request-body scopes are development/test compatibility only."""

    return environment in {"development", "test"}
