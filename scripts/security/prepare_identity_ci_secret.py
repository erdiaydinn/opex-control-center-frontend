"""Prepare the ephemeral Identity Gateway CI key for the image's non-root user.

Docker Compose file-backed secrets are host bind mounts. The CI key generator keeps
private material at mode 0600, so a non-root container cannot read the bind-mounted
file unless ownership is prepared. This helper does not relax the file to world- or
group-readable: it discovers the actual `identity` UID/GID from the built image and
uses a short-lived root helper container to set host-file ownership and mode 0400.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_PATH = ROOT / "runtime" / "identity-gateway" / "signing-private-key.pem"
PROJECT = "opex-identity-ci-gate"
COMPOSE_FILE = ROOT / "docker-compose.platform.yml"
IMAGE_REF = f"{PROJECT}-identity-gateway"

ENV = os.environ.copy()
ENV.update(
    {
        "OPEX_ENVIRONMENT": "test",
        "OPEX_AUTH_MODE": "development",
        "OPEX_INTERNAL_ASSERTION_AUDIENCE": "opex-core-api",
        "OPEX_INTERNAL_SERVICE_ASSERTION_AUDIENCE": "opex-core-preauth",
        "OPEX_IDENTITY_GATEWAY_SIGNING_KID": ENV.get(
            "OPEX_IDENTITY_GATEWAY_SIGNING_KID", "opex-dev-es256-v1"
        ),
        "OPEX_IDENTITY_GATEWAY_SIGNING_KEY_FILE": str(PRIVATE_PATH),
        "OPEX_INTERNAL_ASSERTION_JWKS_SOURCE_FILE": str(
            ROOT / "runtime" / "identity-gateway" / "public-jwks.json"
        ),
    }
)

COMPOSE = [
    "docker",
    "compose",
    "-p",
    PROJECT,
    "-f",
    str(COMPOSE_FILE),
]


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=ENV,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        if capture:
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        raise SystemExit("COMMAND_FAILED=" + " ".join(command[:6]))
    return result


def main() -> None:
    if not PRIVATE_PATH.is_file():
        raise SystemExit("IDENTITY_CI_PRIVATE_KEY_MISSING")

    # Build only the Identity image so its runtime UID/GID is authoritative.
    run([*COMPOSE, "build", "identity-gateway"])

    # Compose gives the service a deterministic project-scoped image reference.
    # Inspect that reference directly instead of parsing version-dependent
    # `docker compose images -q` output (which may be blank or `sha256:`-prefixed).
    run(["docker", "image", "inspect", IMAGE_REF], capture=True)

    owner = run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "root",
            "--entrypoint",
            "sh",
            IMAGE_REF,
            "-c",
            "printf '%s:%s' \"$(id -u identity)\" \"$(id -g identity)\"",
        ],
        capture=True,
    ).stdout.strip()

    if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", owner):
        raise SystemExit("IDENTITY_CI_RUNTIME_OWNER_INVALID=" + repr(owner))

    secret_dir = PRIVATE_PATH.parent.resolve()
    secret_name = PRIVATE_PATH.name

    # The helper container runs as root only to prepare the host bind-mounted
    # ephemeral key. The Identity Gateway itself continues to run non-root.
    run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "root",
            "--entrypoint",
            "sh",
            "-v",
            f"{secret_dir}:/identity-ci-secret:rw",
            IMAGE_REF,
            "-c",
            (
                f"chown {owner} /identity-ci-secret/{secret_name} && "
                f"chmod 0400 /identity-ci-secret/{secret_name}"
            ),
        ]
    )

    info = PRIVATE_PATH.stat()
    uid_text, gid_text = owner.split(":", 1)
    expected_uid = int(uid_text)
    expected_gid = int(gid_text)
    mode = stat.S_IMODE(info.st_mode)

    if info.st_uid != expected_uid or info.st_gid != expected_gid or mode != 0o400:
        raise SystemExit(
            "IDENTITY_CI_SECRET_OWNERSHIP_MISMATCH="
            f"uid:{info.st_uid}/gid:{info.st_gid}/mode:{oct(mode)}"
        )

    print("IDENTITY_CI_NONROOT_SECRET_OWNERSHIP=PASS")
    print("IDENTITY_CI_PRIVATE_KEY_MODE=0400")


if __name__ == "__main__":
    main()
