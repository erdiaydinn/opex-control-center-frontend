from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.authorization import require_permission
from app.core.mobile_fleet_health import (
    FLEET_SNAPSHOT_TTL_SECONDS,
    FleetCredentialIssue,
    FleetCredentialRequest,
    FleetHealthObservation,
    FleetHealthRejected,
    FleetProofInvalid,
    FleetSnapshotConflict,
    FleetTelemetryUnavailable,
    fleet_health_store,
    issue_fleet_credentials,
    validate_observation_freshness,
    verify_fleet_proof,
)
from app.core.security import Principal, get_current_principal

router = APIRouter(prefix="/v1/mobile/fleet", tags=["mobile-fleet"])
FleetManager = Annotated[
    Principal,
    Depends(require_permission("action:workforce:manageDevices")),
]
FleetViewer = Annotated[
    Principal,
    Depends(require_permission("feature:workforce:devices")),
]
FleetReporter = Annotated[Principal, Depends(get_current_principal)]


@router.post("/credentials", status_code=status.HTTP_201_CREATED)
async def post_fleet_credentials(
    payload: FleetCredentialRequest,
    principal: FleetManager,
) -> dict[str, object]:
    try:
        issued: FleetCredentialIssue = issue_fleet_credentials(
            principal.tenant_id,
            payload,
            now_epoch_seconds=int(time.time()),
        )
    except FleetTelemetryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile fleet proof authority is unavailable",
        ) from exc
    except FleetProofInvalid as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        **issued.model_dump(mode="json"),
        "authority": "server_issued_telemetry_correlation_only",
        "operation_authority": False,
        "installation_instruction": "Deliver credentials through managed configuration only",
    }


@router.post("/health", status_code=status.HTTP_202_ACCEPTED)
async def post_fleet_health(
    payload: FleetHealthObservation,
    principal: FleetReporter,
    fleet_proof: Annotated[str, Header(alias="X-EAY-Fleet-Proof", min_length=20, max_length=256)],
) -> dict[str, object]:
    now_ms = int(time.time() * 1000)
    try:
        validate_observation_freshness(payload, now_epoch_ms=now_ms)
        window = verify_fleet_proof(
            principal.tenant_id,
            payload,
            fleet_proof,
            now_epoch_seconds=now_ms // 1000,
        )
        snapshot, idempotent_replay = await fleet_health_store.store_latest(
            principal.tenant_id,
            payload,
            now_epoch_ms=now_ms,
        )
    except FleetProofInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mobile fleet proof is invalid",
        ) from exc
    except FleetHealthRejected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FleetSnapshotConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FleetTelemetryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile fleet telemetry is unavailable",
        ) from exc

    return {
        "accepted": True,
        "idempotent_replay": idempotent_replay,
        "fleet_device_token": payload.fleet_device_token,
        "health": snapshot.health.value,
        "observed_at_epoch_ms": payload.observed_at_epoch_ms,
        "received_at_epoch_ms": snapshot.received_at_epoch_ms,
        "proof_expires_at_epoch_seconds": window.expires_at_epoch_seconds,
        "operation_authority": False,
    }


@router.get("/health")
async def get_fleet_health(
    principal: FleetViewer,
    limit: int = 100,
) -> dict[str, object]:
    now_ms = int(time.time() * 1000)
    try:
        items = await fleet_health_store.list_latest(
            principal.tenant_id,
            now_epoch_ms=now_ms,
            limit=limit,
        )
    except FleetTelemetryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile fleet telemetry is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "retention_seconds": FLEET_SNAPSHOT_TTL_SECONDS,
        "latest_snapshot_only": True,
        "operation_authority": False,
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
    }
