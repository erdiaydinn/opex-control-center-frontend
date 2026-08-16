"""Trusted, tenant-bound grounded retrieval for Core -> EAY AI Core calls.

This router is intentionally separate from the public grounded-chat surface. It
accepts no client-supplied tenant identifier: tenant, membership and actor
identity come only from the dedicated Identity Gateway assertion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from .main import Evidence, KnowledgeLayer, settings
from .tenant_context_assertion import (
    TenantContextAssertionInvalid,
    TenantContextAssertionUnavailable,
    VerifiedTenantContext,
    verify_tenant_context_assertion,
)
from .tenant_context_replay import (
    TenantContextReplayDetected,
    TenantContextReplayGuard,
    TenantContextReplayUnavailable,
)
from .tenant_retrieval import TenantScopedKnowledgeStore

TENANT_CONTEXT_HEADER = "X-EAY-AI-Tenant-Context"


@dataclass(frozen=True)
class TenantContextVerificationSettings:
    jwks_file: str
    issuer: str
    audience: str
    max_lifetime_seconds: int

    @classmethod
    def from_environment(cls) -> "TenantContextVerificationSettings":
        jwks_file = os.getenv("EAY_AI_TENANT_CONTEXT_JWKS_FILE", "").strip()
        issuer = os.getenv(
            "EAY_AI_TENANT_CONTEXT_ISSUER",
            "opex-identity-gateway",
        ).strip()
        audience = os.getenv(
            "EAY_AI_TENANT_CONTEXT_AUDIENCE",
            "eay-ai-core-grounded-retrieval",
        ).strip()
        try:
            max_lifetime_seconds = int(
                os.getenv("EAY_AI_TENANT_CONTEXT_MAX_LIFETIME_SECONDS", "60")
            )
        except ValueError as exc:
            raise TenantContextAssertionUnavailable(
                "tenant-context lifetime configuration invalid"
            ) from exc

        if not jwks_file or not issuer or not audience:
            raise TenantContextAssertionUnavailable(
                "tenant-context verification configuration unavailable"
            )
        if not 1 <= max_lifetime_seconds <= 60:
            raise TenantContextAssertionUnavailable(
                "tenant-context lifetime configuration invalid"
            )
        return cls(
            jwks_file=jwks_file,
            issuer=issuer,
            audience=audience,
            max_lifetime_seconds=max_lifetime_seconds,
        )


class TenantRetrievalRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    as_of: date = Field(default_factory=date.today)
    layers: list[KnowledgeLayer] = Field(min_length=1, max_length=4)
    limit: int = Field(default=8, ge=1, le=32)

    @field_validator("layers")
    @classmethod
    def layers_must_be_unique(
        cls,
        layers: list[KnowledgeLayer],
    ) -> list[KnowledgeLayer]:
        if len(layers) != len(set(layers)):
            raise ValueError("retrieval layers must be unique")
        return layers


class TenantRetrievalResponse(BaseModel):
    evidence: list[Evidence]


router = APIRouter(prefix="/v1/internal/grounded", tags=["internal-grounded"])
tenant_store = TenantScopedKnowledgeStore(settings.db_path)
tenant_context_replay_guard = TenantContextReplayGuard(settings.db_path)


def _verify_header(token: str) -> VerifiedTenantContext:
    if (
        not token
        or len(token) > 8192
        or token != token.strip()
        or "," in token
        or any(character.isspace() for character in token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AI tenant context authentication failed",
        )

    try:
        verifier = TenantContextVerificationSettings.from_environment()
        return verify_tenant_context_assertion(
            token,
            jwks_file=verifier.jwks_file,
            issuer=verifier.issuer,
            audience=verifier.audience,
            max_lifetime_seconds=verifier.max_lifetime_seconds,
        )
    except TenantContextAssertionInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AI tenant context authentication failed",
        ) from exc
    except TenantContextAssertionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tenant context authentication unavailable",
        ) from exc


def _consume_assertion(context: VerifiedTenantContext) -> None:
    try:
        tenant_context_replay_guard.consume(context.assertion_id)
    except TenantContextReplayDetected as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AI tenant context authentication failed",
        ) from exc
    except TenantContextReplayUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tenant context authentication unavailable",
        ) from exc


@router.post("/retrieve", response_model=TenantRetrievalResponse)
async def retrieve_for_verified_tenant(
    request: TenantRetrievalRequest,
    tenant_context_assertion: str = Header(alias=TENANT_CONTEXT_HEADER),
) -> TenantRetrievalResponse:
    context = _verify_header(tenant_context_assertion)
    _consume_assertion(context)
    evidence = tenant_store.search(
        request.message,
        request.as_of,
        request.layers,
        request.limit,
        tenant_id=context.tenant_id,
    )
    return TenantRetrievalResponse(evidence=evidence)
