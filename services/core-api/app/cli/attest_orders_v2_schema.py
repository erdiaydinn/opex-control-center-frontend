"""Explicit opt-in CLI for one live orders-v2 schema metadata observation."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping

from app.core.ai_orders_v2_live_schema_collector import (
    OrdersV2LiveSchemaCollectorConfig,
    build_default_orders_v2_schema_client,
    collect_orders_v2_schema_observation,
)
from app.core.ai_orders_v2_schema_attestation import (
    OrdersV2SchemaAttestationArtifact,
    build_orders_v2_schema_attestation_candidate,
)

EAY_BQ_SCHEMA_ATTESTATION_ENABLED_ENV = (
    "EAY_BQ_SCHEMA_ATTESTATION_ENABLED"
)


class OrdersV2SchemaAttestationDisabled(RuntimeError):
    """Live metadata access requires one explicit invocation opt-in."""


def run_orders_v2_schema_attestation(
    environ: Mapping[str, str] | None = None,
) -> OrdersV2SchemaAttestationArtifact:
    source = os.environ if environ is None else environ
    if (
        source.get(EAY_BQ_SCHEMA_ATTESTATION_ENABLED_ENV, "")
        .strip()
        .lower()
        != "true"
    ):
        raise OrdersV2SchemaAttestationDisabled(
            "live orders schema attestation is not explicitly enabled"
        )

    config = OrdersV2LiveSchemaCollectorConfig.from_environment(source)
    client = build_default_orders_v2_schema_client(config)
    observation = collect_orders_v2_schema_observation(
        client=client,
        config=config,
    )
    return build_orders_v2_schema_attestation_candidate(
        observation
    )


def render_orders_v2_schema_attestation(
    artifact: OrdersV2SchemaAttestationArtifact,
) -> str:
    payload = {
        "artifact": artifact.model_dump(mode="json"),
        "artifact_fingerprint": artifact.artifact_fingerprint,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def main() -> int:
    try:
        artifact = run_orders_v2_schema_attestation()
    except Exception as exc:
        print(
            f"orders-v2 schema attestation failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 2

    print(render_orders_v2_schema_attestation(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
