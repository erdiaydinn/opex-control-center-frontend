"""Environment-driven deployment registry for Jarvis intelligence engines.

Adapters existing in code is not enough to make an engine production-active.
Frontier engines require an explicit enable flag, configured model id, secret
availability and a source-replay-verified benchmark promotion bundle. Plain
attestation objects or environment score/ref assertions cannot activate a
frontier engine. Secret values are only checked for presence and are never
stored in registry state.

The existing EAY Ollama path remains the default local privacy fallback and
uses the existing `EAY_OLLAMA_URL` / `EAY_MODEL` configuration names.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel

from .benchmark_promotion import VerifiedEngineBenchmarkPromotion
from .engine_gateway import EngineEndpoint, EngineProvider, RegisteredEngine
from .intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    Modality,
    PrivacyLevel,
    TaskRisk,
)

ENGINE_REGISTRY_CONTRACT = "eay-engine-deployment-registry-v3"


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _benchmark(environ: Mapping[str, str], prefix: str) -> tuple[float | None, str | None, list[str]]:
    blockers: list[str] = []
    score_raw = environ.get(f"{prefix}_BENCHMARK_SCORE", "").strip()
    evidence_ref = environ.get(f"{prefix}_BENCHMARK_EVIDENCE_REF", "").strip() or None
    if not score_raw or not evidence_ref:
        blockers.append(f"{prefix.casefold()}_benchmark_evidence_missing")
        return None, evidence_ref, blockers
    try:
        score = float(score_raw)
    except ValueError:
        blockers.append(f"{prefix.casefold()}_benchmark_score_invalid")
        return None, evidence_ref, blockers
    if not 0.0 <= score <= 1.0:
        blockers.append(f"{prefix.casefold()}_benchmark_score_out_of_range")
        return None, evidence_ref, blockers
    return score, evidence_ref, blockers


class EngineRegistryState(BaseModel):
    contract: str = ENGINE_REGISTRY_CONTRACT
    registrations: tuple[RegisteredEngine, ...]
    requested_frontier_engines: tuple[str, ...] = ()
    active_frontier_engines: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    secret_values_retained: bool = False

    def by_id(self) -> dict[str, RegisteredEngine]:
        return {item.profile.engine_id: item for item in self.registrations}


def _validate_frontier_promotion(
    *,
    environ: Mapping[str, str],
    prefix: str,
    engine_id: str,
    promotion: VerifiedEngineBenchmarkPromotion | None,
) -> tuple[float | None, str | None, list[str]]:
    blockers: list[str] = []
    if promotion is None:
        return None, None, [f"{prefix.casefold()}_verified_benchmark_promotion_missing"]
    if not isinstance(promotion, VerifiedEngineBenchmarkPromotion):
        return None, None, [f"{prefix.casefold()}_verified_benchmark_promotion_required"]

    attestation = promotion.attestation
    if attestation.engine_id != engine_id or promotion.challenger.system_id != engine_id:
        blockers.append(f"{prefix.casefold()}_benchmark_promotion_engine_mismatch")
    if not attestation.promotion_allowed or attestation.blockers:
        blockers.append(f"{prefix.casefold()}_benchmark_promotion_not_promotable")
    if attestation.critical_safety_regression:
        blockers.append(f"{prefix.casefold()}_benchmark_promotion_safety_regression")

    configured_score = environ.get(f"{prefix}_BENCHMARK_SCORE", "").strip()
    if configured_score:
        try:
            parsed_score = float(configured_score)
        except ValueError:
            blockers.append(f"{prefix.casefold()}_benchmark_score_invalid")
        else:
            if abs(parsed_score - attestation.benchmark_score) > 1e-12:
                blockers.append(f"{prefix.casefold()}_benchmark_score_promotion_mismatch")

    configured_ref = environ.get(f"{prefix}_BENCHMARK_EVIDENCE_REF", "").strip()
    if configured_ref and configured_ref != attestation.evidence_ref:
        blockers.append(f"{prefix.casefold()}_benchmark_evidence_ref_promotion_mismatch")

    if blockers:
        return None, None, blockers
    return attestation.benchmark_score, attestation.evidence_ref, []


def _frontier_registration(
    *,
    environ: Mapping[str, str],
    prefix: str,
    engine_id: str,
    provider: EngineProvider,
    base_url: str,
    secret_env_name: str,
    provider_key: str,
    promotion: VerifiedEngineBenchmarkPromotion | None,
) -> tuple[RegisteredEngine | None, list[str]]:
    if not _enabled(environ.get(f"{prefix}_ENABLED")):
        return None, []

    blockers: list[str] = []
    model_id = environ.get(f"{prefix}_MODEL", "").strip()
    if not model_id:
        blockers.append(f"{prefix.casefold()}_model_id_missing")
    if not environ.get(secret_env_name, "").strip():
        blockers.append(f"{prefix.casefold()}_secret_missing")

    benchmark_score, benchmark_ref, benchmark_blockers = _validate_frontier_promotion(
        environ=environ,
        prefix=prefix,
        engine_id=engine_id,
        promotion=promotion,
    )
    blockers.extend(benchmark_blockers)

    if blockers:
        return None, blockers

    profile = IntelligenceEngine(
        engine_id=engine_id,
        engine_class=EngineClass.FRONTIER,
        modalities=(Modality.TEXT, Modality.CODE),
        supports_tools=False,
        supports_long_horizon=True,
        supports_parallel_delegation=True,
        local_processing=False,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=benchmark_score,
        benchmark_evidence_ref=benchmark_ref,
        independent_provider_key=provider_key,
    )
    endpoint = EngineEndpoint(
        engine_id=engine_id,
        provider=provider,
        model_id=model_id,
        base_url=base_url,
        secret_ref=f"env:{secret_env_name}",
    )
    return RegisteredEngine(profile=profile, endpoint=endpoint), []


def build_engine_registry(
    environ: Mapping[str, str],
    *,
    benchmark_promotions: Mapping[str, VerifiedEngineBenchmarkPromotion] | None = None,
) -> EngineRegistryState:
    registrations: list[RegisteredEngine] = []
    blockers: list[str] = []
    requested: list[str] = []
    active: list[str] = []
    promotions = benchmark_promotions or {}

    if _enabled(environ.get("EAY_OLLAMA_ENABLED"), default=True):
        local_score, local_ref, _ = _benchmark(environ, "EAY_OLLAMA")
        registrations.append(
            RegisteredEngine(
                profile=IntelligenceEngine(
                    engine_id="ollama-local",
                    engine_class=EngineClass.LOCAL,
                    modalities=(Modality.TEXT, Modality.CODE),
                    supports_tools=False,
                    supports_long_horizon=False,
                    supports_parallel_delegation=False,
                    local_processing=True,
                    maximum_privacy=PrivacyLevel.RESTRICTED,
                    maximum_risk=TaskRisk.CRITICAL,
                    exact_adapter_verified=True,
                    production_enabled=True,
                    benchmark_score=local_score,
                    benchmark_evidence_ref=local_ref if local_score is not None else None,
                    independent_provider_key="ollama-local",
                ),
                endpoint=EngineEndpoint(
                    engine_id="ollama-local",
                    provider=EngineProvider.OLLAMA,
                    model_id=environ.get("EAY_MODEL", "eay-ops:0.1").strip() or "eay-ops:0.1",
                    base_url=environ.get("EAY_OLLAMA_URL", "http://ollama:11434").strip() or "http://ollama:11434",
                    allow_remote_local_engine=True,
                ),
            )
        )

    specs = (
        (
            "EAY_OPENAI",
            "openai-frontier",
            EngineProvider.OPENAI_RESPONSES,
            "https://api.openai.com",
            "OPENAI_API_KEY",
            "openai",
        ),
        (
            "EAY_ANTHROPIC",
            "anthropic-frontier",
            EngineProvider.ANTHROPIC_MESSAGES,
            "https://api.anthropic.com",
            "ANTHROPIC_API_KEY",
            "anthropic",
        ),
        (
            "EAY_GEMINI",
            "gemini-frontier",
            EngineProvider.GEMINI_GENERATE_CONTENT,
            "https://generativelanguage.googleapis.com",
            "GEMINI_API_KEY",
            "google-gemini",
        ),
    )
    for prefix, engine_id, provider, base_url, secret_name, provider_key in specs:
        if _enabled(environ.get(f"{prefix}_ENABLED")):
            requested.append(engine_id)
        registration, item_blockers = _frontier_registration(
            environ=environ,
            prefix=prefix,
            engine_id=engine_id,
            provider=provider,
            base_url=base_url,
            secret_env_name=secret_name,
            provider_key=provider_key,
            promotion=promotions.get(engine_id),
        )
        blockers.extend(item_blockers)
        if registration is not None:
            registrations.append(registration)
            active.append(engine_id)

    return EngineRegistryState(
        registrations=tuple(registrations),
        requested_frontier_engines=tuple(requested),
        active_frontier_engines=tuple(active),
        blockers=tuple(dict.fromkeys(blockers)),
    )
