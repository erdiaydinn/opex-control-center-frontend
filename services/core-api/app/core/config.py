import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.internal_service_replay import (
    INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS,
    INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEX_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://opex_runtime:change-this-runtime-password@postgres:5432/opex"
    )
    database_url_file: str = ""

    migration_database_url: str = (
        "postgresql+asyncpg://opex_migrator:change-this-migration-password@postgres:5432/opex"
    )
    migration_database_url_file: str = ""

    redis_url: str = "redis://redis:6379/0"

    auth_mode: Literal["development", "oidc", "internal_assertion"] = "development"
    oidc_issuer: str = ""
    oidc_audience: str = "opex-core-api"
    oidc_jwks_url: str = ""
    oidc_tenant_claim: str = "tenant_id"
    oidc_roles_claim: str = "roles"
    oidc_algorithms: str = "RS256,ES256"

    internal_assertion_issuer: str = ""
    internal_assertion_audience: str = "opex-core-api"
    internal_service_assertion_audience: str = "opex-core-preauth"
    internal_assertion_jwks_file: str = ""
    internal_assertion_algorithms: str = "ES256"
    internal_assertion_max_lifetime_seconds: int = 60

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

    @property
    def internal_assertion_algorithm_list(self) -> list[str]:
        return [
            value.strip()
            for value in self.internal_assertion_algorithms.split(",")
            if value.strip()
        ]

    @model_validator(mode="after")
    def validate_security_posture(self) -> "Settings":
        if self.database_url_file:
            secret_path = Path(self.database_url_file)

            try:
                database_url = secret_path.read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                raise ValueError(
                    "Runtime database secret file cannot be read"
                ) from exc

            if not database_url:
                raise ValueError(
                    "Runtime database secret file is empty"
                )

            self.database_url = database_url

        if self.migration_database_url_file:
            secret_path = Path(self.migration_database_url_file)

            try:
                migration_database_url = secret_path.read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                raise ValueError(
                    "Migration database secret file cannot be read"
                ) from exc

            if not migration_database_url:
                raise ValueError(
                    "Migration database secret file is empty"
                )

            self.migration_database_url = migration_database_url
        if (
            self.environment in {"staging", "production"}
            and self.auth_mode not in {"oidc", "internal_assertion"}
        ):
            raise ValueError(
                "Staging and production require OPEX_AUTH_MODE=oidc or internal_assertion"
            )

        allowed_oidc_algorithms = {"RS256", "ES256"}
        configured_algorithms = set(self.oidc_algorithm_list)

        if not configured_algorithms:
            raise ValueError("At least one OIDC signing algorithm is required")

        unsupported_algorithms = configured_algorithms - allowed_oidc_algorithms
        if unsupported_algorithms:
            raise ValueError(
                "Unsupported OIDC signing algorithms: "
                + ", ".join(sorted(unsupported_algorithms))
            )

        if self.auth_mode == "oidc":
            if self.environment in {"staging", "production"}:
                if not self.oidc_issuer.startswith("https://"):
                    raise ValueError(
                        "OIDC issuer must use HTTPS in staging and production"
                    )

                if not self.oidc_jwks_url.startswith("https://"):
                    raise ValueError(
                        "OIDC JWKS URL must use HTTPS in staging and production"
                    )

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

        if not self.internal_service_assertion_audience.strip():
            raise ValueError(
                "Internal service assertion audience is required"
            )

        if (
            self.internal_service_assertion_audience
            == self.internal_assertion_audience
        ):
            raise ValueError(
                "Internal service assertion audience must differ "
                "from end-user assertion audience"
            )

        allowed_internal_assertion_algorithms = {
            "ES256",
        }

        configured_internal_algorithms = set(
            self.internal_assertion_algorithm_list
        )

        if not configured_internal_algorithms:
            raise ValueError(
                "At least one internal assertion "
                "signing algorithm is required"
            )

        unsupported_internal_algorithms = (
            configured_internal_algorithms
            - allowed_internal_assertion_algorithms
        )

        if unsupported_internal_algorithms:
            raise ValueError(
                "Unsupported internal assertion algorithms: "
                + ", ".join(
                    sorted(
                        unsupported_internal_algorithms
                    )
                )
            )

        if not (
            15
            <= self.internal_assertion_max_lifetime_seconds
            <= 60
        ):
            raise ValueError(
                "Internal assertion maximum lifetime "
                "must be between 15 and 60 seconds"
            )

        replay_retention_seconds = (
            self.internal_assertion_max_lifetime_seconds
            + INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS
        )

        if (
            replay_retention_seconds
            > INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS
        ):
            raise ValueError(
                "Internal assertion lifetime exceeds "
                "replay retention capacity"
            )

        if self.auth_mode == "internal_assertion":
            missing_internal = [
                name
                for name, value in {
                    "OPEX_INTERNAL_ASSERTION_ISSUER":
                        self.internal_assertion_issuer,
                    "OPEX_INTERNAL_ASSERTION_AUDIENCE":
                        self.internal_assertion_audience,
                    "OPEX_INTERNAL_ASSERTION_JWKS_FILE":
                        self.internal_assertion_jwks_file,
                }.items()
                if not str(value).strip()
            ]

            if missing_internal:
                raise ValueError(
                    "Internal assertion configuration "
                    "is incomplete: "
                    + ", ".join(missing_internal)
                )

            jwks_path = Path(
                self.internal_assertion_jwks_file
            )

            if not jwks_path.is_file():
                raise ValueError(
                    "Internal assertion JWKS file "
                    "cannot be read"
                )

        if self.environment == "production" and "*" in self.cors_origin_list:
            raise ValueError("Wildcard CORS is forbidden in production")

        if self.environment in {"staging", "production"}:
            if "*" in self.allowed_host_list:
                raise ValueError(
                    "Wildcard allowed host is forbidden in staging and production"
                )

            insecure_origins = [
                origin
                for origin in self.cors_origin_list
                if not origin.startswith("https://")
            ]
            if insecure_origins:
                raise ValueError(
                    "CORS origins must use HTTPS in staging and production"
                )

        if self.environment == "production":
            forbidden_hosts = {"localhost", "127.0.0.1", "::1"}
            if forbidden_hosts.intersection(self.allowed_host_list):
                raise ValueError(
                    "Localhost allowed hosts are forbidden in production"
                )

            local_origin_prefixes = (
                "http://localhost",
                "https://localhost",
                "http://127.0.0.1",
                "https://127.0.0.1",
                "http://[::1]",
                "https://[::1]",
            )
            if any(
                origin.startswith(local_origin_prefixes)
                for origin in self.cors_origin_list
            ):
                raise ValueError(
                    "Localhost CORS origins are forbidden in production"
                )

        if self.environment in {"staging", "production"}:
            forbidden_secret_env = [
                name
                for name in (
                    "OPEX_DATABASE_URL",
                    "OPEX_MIGRATION_DATABASE_URL",
                )
                if os.getenv(name, "").strip()
            ]

            if forbidden_secret_env:
                raise ValueError(
                    "Database credentials must not be supplied through "
                    "environment variables in staging or production"
                )

            if (
                not self.database_url_file
                and not self.migration_database_url_file
            ):
                raise ValueError(
                    "Staging and production require database credentials "
                    "from secret files"
                )

        if self.database_url == self.migration_database_url:
            raise ValueError("Runtime and migration database credentials must differ")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
