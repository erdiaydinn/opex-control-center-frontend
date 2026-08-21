"""Version-controlled downstream query-contract readiness for Jarvis tools.

Platform authorization alone cannot prove that a downstream analytics query
contains the tenant/entity predicate needed for end-to-end isolation. This
registry therefore keeps staging/production execution fail-closed until an
exact reviewed query template fingerprint, tenant discriminator parameter and
data-scope adapter are all pinned in code review.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_tool_authorization import AiToolName

SHA256_PATTERN = r"^[0-9a-f]{64}$"
Environment = Literal[
    "development",
    "test",
    "staging",
    "production",
]


class AiQueryContractPolicyError(RuntimeError):
    """Base error for downstream query-contract policy."""


class AiQueryContractNotReady(AiQueryContractPolicyError):
    """The tool has no production-approved downstream query contract."""


class AiQueryContractPolicy(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    tool: AiToolName
    contract_id: str = Field(
        min_length=1,
        max_length=160,
    )
    contract_revision: int = Field(ge=1)
    data_scope_argument: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    tenant_discriminator_parameter: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    query_template_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    review_fingerprint: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    production_ready: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_readiness(self) -> AiQueryContractPolicy:
        if self.production_ready:
            missing = [
                name
                for name, value in {
                    "data_scope_argument": self.data_scope_argument,
                    "tenant_discriminator_parameter": (
                        self.tenant_discriminator_parameter
                    ),
                    "query_template_sha256": self.query_template_sha256,
                    "review_fingerprint": self.review_fingerprint,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(
                    "Production-ready AI query contract is incomplete: "
                    + ", ".join(missing)
                )
            if self.blockers:
                raise ValueError(
                    "Production-ready AI query contract cannot have blockers"
                )
        elif not self.blockers:
            raise ValueError(
                "Blocked AI query contract must explain its blockers"
            )

        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError(
                "AI query contract blockers must be unique"
            )

        return self


def _review_fingerprint_payload(
    policy: AiQueryContractPolicy,
) -> dict[str, object]:
    return {
        "tool": policy.tool,
        "contract_id": policy.contract_id,
        "contract_revision": policy.contract_revision,
        "data_scope_argument": policy.data_scope_argument,
        "tenant_discriminator_parameter": (
            policy.tenant_discriminator_parameter
        ),
        "query_template_sha256": policy.query_template_sha256,
    }


def expected_query_contract_review_fingerprint(
    policy: AiQueryContractPolicy,
) -> str:
    """Bind reviewed readiness to the exact query-contract security fields."""

    encoded = json.dumps(
        _review_fingerprint_payload(policy),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ai_query_contract_policy_fingerprint(
    policy: AiQueryContractPolicy,
) -> str:
    """Fingerprint the full version-controlled policy, including blockers."""

    encoded = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ai_execution_scope_fingerprint(
    *,
    query_contract_fingerprint: str,
    data_scope_fingerprint: str,
    tenant_query_context_fingerprint: str,
) -> str:
    """Bind query semantics, role data scope, and tenant query identity."""

    fields = {
        "query_contract_fingerprint": query_contract_fingerprint,
        "data_scope_fingerprint": data_scope_fingerprint,
        "tenant_query_context_fingerprint": (
            tenant_query_context_fingerprint
        ),
    }
    for name, value in fields.items():
        if (
            len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError(f"{name} must be lowercase SHA-256")

    encoded = json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# IMPORTANT: this registry is intentionally blocked today. The frozen EAY AI
# Core v0.1 `ops.kpi.orders.v1` template has a store filter but no reviewed
# tenant/entity discriminator contract. Catalog/regulatory tools also lack a
# reviewed enforceable data-scope adapter. A future PR may flip a record to
# production_ready=True only by pinning exact reviewed fingerprints here.
AI_QUERY_CONTRACT_POLICIES = MappingProxyType(
    {
        "ops_kpi_query": AiQueryContractPolicy(
            tool="ops_kpi_query",
            contract_id="ops.kpi.orders.v1",
            contract_revision=1,
            data_scope_argument="stores",
            tenant_discriminator_parameter=None,
            query_template_sha256=None,
            review_fingerprint=None,
            production_ready=False,
            blockers=(
                "tenant_discriminator_not_reviewed",
                "query_template_fingerprint_not_pinned",
            ),
        ),
        "catalog_query": AiQueryContractPolicy(
            tool="catalog_query",
            contract_id="catalog.lookup.v1",
            contract_revision=1,
            data_scope_argument=None,
            tenant_discriminator_parameter=None,
            query_template_sha256=None,
            review_fingerprint=None,
            production_ready=False,
            blockers=(
                "data_scope_adapter_not_reviewed",
                "tenant_discriminator_not_reviewed",
                "query_template_fingerprint_not_pinned",
            ),
        ),
        "regulatory_impact_query": AiQueryContractPolicy(
            tool="regulatory_impact_query",
            contract_id="regulatory.impact.v1",
            contract_revision=1,
            data_scope_argument=None,
            tenant_discriminator_parameter=None,
            query_template_sha256=None,
            review_fingerprint=None,
            production_ready=False,
            blockers=(
                "data_scope_adapter_not_reviewed",
                "tenant_discriminator_not_reviewed",
                "query_template_fingerprint_not_pinned",
            ),
        ),
    }
)


def get_ai_query_contract_policy(
    tool: AiToolName,
) -> AiQueryContractPolicy:
    try:
        return AI_QUERY_CONTRACT_POLICIES[tool]
    except KeyError as exc:
        raise AiQueryContractPolicyError(
            "unsupported_ai_query_contract"
        ) from exc


def require_ai_query_contract_ready(
    *,
    tool: AiToolName,
    environment: Environment,
) -> AiQueryContractPolicy:
    """Block staging/production until the reviewed downstream contract exists."""

    policy = get_ai_query_contract_policy(tool)

    if environment in {"staging", "production"}:
        if not policy.production_ready:
            raise AiQueryContractNotReady(
                "ai_query_contract_not_ready"
            )

        expected_review = expected_query_contract_review_fingerprint(
            policy
        )
        if policy.review_fingerprint != expected_review:
            raise AiQueryContractNotReady(
                "ai_query_contract_review_fingerprint_mismatch"
            )

    return policy
