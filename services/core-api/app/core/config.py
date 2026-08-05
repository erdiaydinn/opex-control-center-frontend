from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEX_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://opex_app:change-this-local-password@postgres:5432/opex"
    redis_url: str = "redis://redis:6379/0"

    auth_mode: Literal["development", "oidc"] = "development"
    oidc_issuer: str = ""
    oidc_audience: str = "opex-core-api"
    oidc_jwks_url: str = ""
    oidc_tenant_claim: str = "tenant_id"
    oidc_roles_claim: str = "roles"
    oidc_algorithms: str = "RS256,ES256"

    allowed_hosts: str = "localhost,127.0.0.1,core-api,gateway"
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"

    ai_provider: Literal["ollama", "disabled"] = "ollama"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:8b"
    external_ai_enabled: bool = False

    @property
    def allowed_host_list(self) -> list[str]:
        return [value.strip() for value in self.allowed_hosts.split(",") if value.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def oidc_algorithm_list(self) -> list[str]:
        return [value.strip() for value in self.oidc_algorithms.split(",") if value.strip()]

    @model_validator(mode="after")
    def validate_security_posture(self) -> "Settings":
        if self.environment == "production" and self.auth_mode != "oidc":
            raise ValueError("Production requires OPEX_AUTH_MODE=oidc")

        if self.auth_mode == "oidc":
            missing = [
                name
                for name, value in {
                    "OPEX_OIDC_ISSUER": self.oidc_issuer,
                    "OPEX_OIDC_AUDIENCE": self.oidc_audience,
                    "OPEX_OIDC_JWKS_URL": self.oidc_jwks_url,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"OIDC configuration is incomplete: {', '.join(missing)}")

        if self.environment == "production" and "*" in self.cors_origin_list:
            raise ValueError("Wildcard CORS is forbidden in production")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
