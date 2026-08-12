"""Operator-only public JWKS export and rotation support for EAY Jarvis.

The private signing key remains an input-only secret. This module never emits
private key material and never prints JWKS content to stdout. Rotation is
performed by merging the new public key with an explicitly supplied existing
public JWKS, allowing a bounded verification overlap window.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jwt.algorithms import ECAlgorithm

from .jarvis_service_identity import (
    JARVIS_SERVICE_ALGORITHM,
    KID_PATTERN,
    JarvisServiceIdentityError,
    JarvisServiceIdentitySettings,
    JarvisServiceIdentitySigner,
)

MAX_JWKS_KEYS = 16
_ALLOWED_JWK_FIELDS = {
    "kty",
    "crv",
    "x",
    "y",
    "kid",
    "use",
    "alg",
}


class JarvisJwksExportError(RuntimeError):
    """Public JWKS export or rotation input is unsafe or invalid."""


def _validate_public_jwk(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise JarvisJwksExportError("JWKS key entry must be an object")

    if set(value) != _ALLOWED_JWK_FIELDS:
        raise JarvisJwksExportError(
            "Jarvis public JWK fields do not match the approved contract"
        )

    if "d" in value:
        raise JarvisJwksExportError(
            "Private key material is forbidden in Jarvis JWKS"
        )

    if (
        value.get("kty") != "EC"
        or value.get("crv") != "P-256"
        or value.get("alg") != JARVIS_SERVICE_ALGORITHM
        or value.get("use") != "sig"
    ):
        raise JarvisJwksExportError(
            "Jarvis public JWK cryptographic contract is invalid"
        )

    kid = value.get("kid")
    if not isinstance(kid, str) or not KID_PATTERN.fullmatch(kid):
        raise JarvisJwksExportError("Jarvis public JWK kid is invalid")

    for coordinate in ("x", "y"):
        encoded = value.get(coordinate)
        if not isinstance(encoded, str) or not encoded:
            raise JarvisJwksExportError(
                "Jarvis public JWK coordinate is invalid"
            )

    try:
        ECAlgorithm.from_jwk(value)
    except (TypeError, ValueError) as exc:
        raise JarvisJwksExportError(
            "Jarvis public JWK cannot be decoded"
        ) from exc

    return {field: str(value[field]) for field in _ALLOWED_JWK_FIELDS}


def _load_public_jwks(path: Path) -> list[dict[str, str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JarvisJwksExportError(
            "Existing Jarvis public JWKS cannot be read"
        ) from exc

    if not isinstance(raw, dict) or set(raw) != {"keys"}:
        raise JarvisJwksExportError(
            "Existing Jarvis JWKS root is invalid"
        )

    keys = raw.get("keys")
    if not isinstance(keys, list) or not keys:
        raise JarvisJwksExportError(
            "Existing Jarvis JWKS must contain verification keys"
        )

    if len(keys) > MAX_JWKS_KEYS:
        raise JarvisJwksExportError(
            "Existing Jarvis JWKS exceeds verification-key capacity"
        )

    return [_validate_public_jwk(item) for item in keys]


def _public_key_identity(key: dict[str, str]) -> tuple[str, str, str]:
    return (key["crv"], key["x"], key["y"])


def build_rotation_jwks(
    current_public_jwks: dict[str, object],
    *,
    existing_public_jwks_file: Path | None = None,
) -> dict[str, list[dict[str, str]]]:
    current_keys = current_public_jwks.get("keys")
    if (
        not isinstance(current_public_jwks, dict)
        or set(current_public_jwks) != {"keys"}
        or not isinstance(current_keys, list)
        or len(current_keys) != 1
    ):
        raise JarvisJwksExportError(
            "Current Jarvis signer must export exactly one public key"
        )

    current = _validate_public_jwk(current_keys[0])
    merged: list[dict[str, str]] = [current]
    by_kid = {current["kid"]: current}

    if existing_public_jwks_file is not None:
        for key in _load_public_jwks(existing_public_jwks_file):
            previous = by_kid.get(key["kid"])
            if previous is not None:
                if _public_key_identity(previous) != _public_key_identity(key):
                    raise JarvisJwksExportError(
                        "Jarvis JWKS contains a conflicting duplicate kid"
                    )
                continue

            merged.append(key)
            by_kid[key["kid"]] = key

    if len(merged) > MAX_JWKS_KEYS:
        raise JarvisJwksExportError(
            "Rotated Jarvis JWKS exceeds verification-key capacity"
        )

    return {"keys": merged}


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return os.path.abspath(left) == os.path.abspath(right)


def write_public_jwks_atomic(
    *,
    output_file: Path,
    jwks: dict[str, object],
    replace: bool,
) -> None:
    parent = output_file.parent
    if not parent.exists() or not parent.is_dir():
        raise JarvisJwksExportError(
            "JWKS output directory must already exist"
        )

    if output_file.exists() and not replace:
        raise JarvisJwksExportError(
            "JWKS output already exists; explicit --replace is required"
        )

    encoded = (
        json.dumps(
            jwks,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")

    temp_path: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temp_path = Path(temp_name)
        try:
            os.fchmod(descriptor, 0o644)
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise

        os.replace(temp_path, output_file)
        temp_path = None

        try:
            directory_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    except OSError as exc:
        raise JarvisJwksExportError(
            "Jarvis public JWKS could not be written atomically"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def export_public_jwks(
    *,
    private_key_file: Path,
    signing_kid: str,
    output_file: Path,
    merge_existing_file: Path | None = None,
    replace: bool = False,
) -> dict[str, list[dict[str, str]]]:
    if _same_path(private_key_file, output_file):
        raise JarvisJwksExportError(
            "Public JWKS output must not overwrite the private key"
        )

    if merge_existing_file is not None and _same_path(
        private_key_file,
        merge_existing_file,
    ):
        raise JarvisJwksExportError(
            "Private key must not be parsed as an existing JWKS"
        )

    try:
        settings = JarvisServiceIdentitySettings(
            private_key_file=str(private_key_file),
            signing_kid=signing_kid,
        )
        signer = JarvisServiceIdentitySigner(settings)
        current_public_jwks = signer.public_jwks()
    except JarvisServiceIdentityError as exc:
        raise JarvisJwksExportError(
            "Jarvis private signing key cannot produce public JWKS"
        ) from exc

    jwks = build_rotation_jwks(
        current_public_jwks,
        existing_public_jwks_file=merge_existing_file,
    )
    write_public_jwks_atomic(
        output_file=output_file,
        jwks=jwks,
        replace=replace,
    )
    return jwks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export public-only EAY Jarvis JWKS from an existing private "
            "signing key. JWKS content is written only to --output."
        )
    )
    parser.add_argument("--private-key-file", required=True, type=Path)
    parser.add_argument("--kid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--merge-existing",
        type=Path,
        default=None,
        help=(
            "Optional existing public JWKS to retain during a bounded key "
            "rotation overlap."
        ),
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly allow replacing an existing output JWKS file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    jwks = export_public_jwks(
        private_key_file=args.private_key_file,
        signing_kid=args.kid,
        output_file=args.output,
        merge_existing_file=args.merge_existing,
        replace=args.replace,
    )
    kids = ",".join(key["kid"] for key in jwks["keys"])
    print(f"Jarvis public JWKS written: {args.output} (kids={kids})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
