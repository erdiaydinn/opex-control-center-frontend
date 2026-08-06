import json
import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

DOCKER_API_URL = os.getenv(
    "DOCKER_API_URL",
    "http://docker-socket-proxy:2375",
)

app = FastAPI(
    title="EAY OneOps Platform Agent",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/containers")
async def containers() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                f"{DOCKER_API_URL}/containers/json",
                params={
                    "all": "true",
                    "filters": '{"label":["com.docker.compose.project=opex-platform"]}',
                },
            )
            response.raise_for_status()
            docker_containers = response.json()

        items = []

        for container in docker_containers:
            names = container.get("Names") or []
            name = names[0].lstrip("/") if names else container.get("Id", "")[:12]

            state = container.get("State", "unknown")
            status_text = container.get("Status", "")
            health = "unknown"

            lowered = status_text.lower()

            if "(healthy)" in lowered:
                health = "healthy"
            elif "(unhealthy)" in lowered:
                health = "unhealthy"
            elif state == "running":
                health = "running"
            elif state == "exited":
                health = "stopped"

            items.append(
                {
                    "id": container.get("Id", "")[:12],
                    "name": name,
                    "image": container.get("Image", ""),
                    "state": state,
                    "health": health,
                    "status": status_text,
                    "created": container.get("Created"),
                }
            )

        running = sum(1 for item in items if item["state"] == "running")
        unhealthy = sum(
            1
            for item in items
            if item["health"] == "unhealthy"
            or item["state"] in {"restarting", "dead"}
        )

        return JSONResponse(
            content={
                "status": "ok" if unhealthy == 0 else "degraded",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total": len(items),
                    "running": running,
                    "stopped": len(items) - running,
                    "unhealthy": unhealthy,
                },
                "containers": items,
            }
        )

    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "Docker service information is unavailable",
            },
        )

@app.get("/v1/backups/status")
async def backup_status() -> JSONResponse:
    status_file = os.getenv(
        "BACKUP_STATUS_FILE",
        "/backups/backup-status.json",
    )

    try:
        with open(status_file, "r", encoding="utf-8") as file:
            backup = json.load(file)

        return JSONResponse(
            content={
                "status": backup.get("status", "unknown"),
                "database": backup.get("database"),
                "started_at": backup.get("started_at"),
                "completed_at": backup.get("completed_at"),
                "filename": backup.get("filename"),
                "size_bytes": backup.get("size_bytes", 0),
                "retention_days": backup.get("retention_days"),
                "interval_hours": backup.get("interval_hours"),
                "message": backup.get("message", ""),
            }
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "detail": "No backup status has been recorded yet",
            },
        )
    except (OSError, json.JSONDecodeError):
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "Backup status information is unavailable",
            },
        )
