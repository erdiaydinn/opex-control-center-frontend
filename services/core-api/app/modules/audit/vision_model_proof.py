from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProductionModelProof(BaseModel):
    """Opaque snapshot of EAY AI Core's re-verified current-production proof."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_record_id: str = Field(min_length=1, max_length=180)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_provenance_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    production_promotion_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    production_release_proof_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProductionModelProofUnavailable(RuntimeError):
    pass


class ProductionModelProofVerifier(Protocol):
    async def require_current_production(self, model_record_id: str) -> ProductionModelProof: ...


class UnavailableProductionModelProofVerifier:
    """Default fail-closed verifier until the governed AI Core proof adapter is configured."""

    async def require_current_production(self, model_record_id: str) -> ProductionModelProof:
        del model_record_id
        raise ProductionModelProofUnavailable("canonical production model proof is unavailable")
