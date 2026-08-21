from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx
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


DEFAULT_TRUSTED_AI_HOSTS = frozenset({"eay-ai-core", "localhost"})


def _normalized_ai_core_url(
    value: str,
    *,
    trusted_hosts: frozenset[str] = DEFAULT_TRUSTED_AI_HOSTS,
) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    hostname = (parsed.hostname or "").lower()
    try:
        loopback = ip_address(hostname).is_loopback
    except ValueError:
        loopback = False
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (hostname not in trusted_hosts and not loopback)
    ):
        raise ValueError("AI Core model proof URL is invalid")
    return value.strip().rstrip("/")


def _sealed_payload(body: dict[str, object]) -> bytes:
    payload = {key: value for key, value in body.items() if key != "seal"}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class AICoreProductionModelProofVerifier:
    """Challenge-bound adapter to AI Core's current model lifecycle authority."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        client: httpx.AsyncClient | None = None,
        trusted_hosts: frozenset[str] = DEFAULT_TRUSTED_AI_HOSTS,
    ) -> None:
        if len(token) < 32 or token != token.strip():
            raise ValueError("AI Core model proof token is invalid")
        self.base_url = _normalized_ai_core_url(base_url, trusted_hosts=trusted_hosts)
        self.token = token
        self.client = client

    async def require_current_production(self, model_record_id: str) -> ProductionModelProof:
        if not model_record_id or len(model_record_id) > 180:
            raise ProductionModelProofUnavailable("canonical production model proof is unavailable")
        challenge = secrets.token_hex(32)
        url = (
            self.base_url
            + "/v1/internal/model-production-proofs/"
            + quote(model_record_id, safe="")
        )
        owns_client = self.client is None
        active_client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        try:
            response = await active_client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "X-EAY-Model-Proof-Challenge": challenge,
                },
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise ProductionModelProofUnavailable(
                "canonical production model proof is unavailable"
            ) from exc
        finally:
            if owns_client:
                await active_client.aclose()
        if response.status_code != 200:
            raise ProductionModelProofUnavailable("canonical production model proof is unavailable")
        try:
            body = response.json()
            expected_fields = {
                "model_record_id",
                "artifact_sha256",
                "artifact_provenance_fingerprint",
                "production_promotion_fingerprint",
                "production_release_proof_fingerprint",
                "challenge",
                "issued_at",
                "expires_at",
                "seal",
            }
            if not isinstance(body, dict) or set(body) != expected_fields:
                raise ValueError("model proof response shape mismatch")
            issued_at = datetime.fromisoformat(str(body["issued_at"]))
            expires_at = datetime.fromisoformat(str(body["expires_at"]))
            now = datetime.now(UTC)
            expected_seal = hmac.new(
                self.token.encode("utf-8"),
                _sealed_payload(body),
                hashlib.sha256,
            ).hexdigest()
            if (
                body["model_record_id"] != model_record_id
                or body["challenge"] != challenge
                or issued_at.tzinfo is None
                or expires_at.tzinfo is None
                or issued_at > now
                or expires_at <= now
                or (expires_at - issued_at).total_seconds() > 30
                or not hmac.compare_digest(str(body["seal"]), expected_seal)
            ):
                raise ValueError("model proof response binding mismatch")
            proof_fields = {
                key: body[key] for key in ProductionModelProof.model_fields
            }
            return ProductionModelProof(**proof_fields)
        except (TypeError, ValueError) as exc:
            raise ProductionModelProofUnavailable(
                "canonical production model proof is unavailable"
            ) from exc


def configured_production_model_proof_verifier() -> ProductionModelProofVerifier:
    """Build the production adapter only from explicit server-side configuration."""

    base_url = os.getenv("EAY_AI_CORE_URL", "").strip()
    token = os.getenv("EAY_MODEL_PROOF_API_TOKEN", "")
    if not base_url or not token:
        return UnavailableProductionModelProofVerifier()
    try:
        return AICoreProductionModelProofVerifier(base_url=base_url, token=token)
    except ValueError:
        return UnavailableProductionModelProofVerifier()
