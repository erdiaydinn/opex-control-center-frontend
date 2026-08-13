"""Deliver Employee Master exit revocations to the corporate OIDC adapter."""

import os

import httpx

from app.modules.workforce import persistence


def run_once() -> dict:
    endpoint = os.getenv("OPEX_OIDC_REVOCATION_URL", "").strip()
    token = os.getenv("OPEX_OIDC_REVOCATION_TOKEN", "").strip()
    if not endpoint or not token:
        raise RuntimeError("OPEX_OIDC_REVOCATION_URL ve OPEX_OIDC_REVOCATION_TOKEN zorunludur")
    delivered = failed = 0
    for row in persistence.claim_identity_revocations():
        error = None
        try:
            response = httpx.post(
                endpoint,
                json=row["payload"],
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": row["id"]},
                timeout=20,
            )
            response.raise_for_status()
        except Exception as exc:
            error = str(exc)
        persistence.finish_identity_revocation(row["id"], error)
        if error:
            failed += 1
        else:
            delivered += 1
    return {"delivered": delivered, "failed": failed}


if __name__ == "__main__":
    print(run_once())
