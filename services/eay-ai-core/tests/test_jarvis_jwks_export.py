from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.jarvis_jwks_export import (
    MAX_JWKS_KEYS,
    JarvisJwksExportError,
    build_rotation_jwks,
    export_public_jwks,
    main,
)
from app.jarvis_service_identity import (
    JarvisServiceIdentitySettings,
    JarvisServiceIdentitySigner,
)


def write_private_key(path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def public_jwks(private_key: Path, kid: str) -> dict[str, object]:
    return JarvisServiceIdentitySigner(
        JarvisServiceIdentitySettings(
            private_key_file=str(private_key),
            signing_kid=kid,
        )
    ).public_jwks()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True),
        encoding="utf-8",
    )


def test_bootstrap_exports_public_only_jwks_atomically(tmp_path: Path) -> None:
    private_key = tmp_path / "jarvis-private.pem"
    output = tmp_path / "jarvis-public.jwks.json"
    write_private_key(private_key)

    exported = export_public_jwks(
        private_key_file=private_key,
        signing_kid="jarvis-2026-08-v1",
        output_file=output,
    )

    on_disk = json.loads(output.read_text(encoding="utf-8"))
    assert on_disk == exported
    assert len(on_disk["keys"]) == 1
    assert on_disk["keys"][0]["kid"] == "jarvis-2026-08-v1"
    assert "d" not in on_disk["keys"][0]
    assert "BEGIN PRIVATE KEY" not in output.read_text(encoding="utf-8")
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o644


def test_export_refuses_implicit_overwrite(tmp_path: Path) -> None:
    private_key = tmp_path / "jarvis-private.pem"
    output = tmp_path / "jarvis-public.jwks.json"
    write_private_key(private_key)

    export_public_jwks(
        private_key_file=private_key,
        signing_kid="kid-v1",
        output_file=output,
    )

    with pytest.raises(JarvisJwksExportError):
        export_public_jwks(
            private_key_file=private_key,
            signing_kid="kid-v1",
            output_file=output,
        )

    export_public_jwks(
        private_key_file=private_key,
        signing_kid="kid-v1",
        output_file=output,
        replace=True,
    )


def test_rotation_retains_old_public_key_for_overlap(tmp_path: Path) -> None:
    old_private = tmp_path / "old.pem"
    new_private = tmp_path / "new.pem"
    output = tmp_path / "jarvis.jwks.json"
    write_private_key(old_private)
    write_private_key(new_private)
    write_json(output, public_jwks(old_private, "kid-old"))

    rotated = export_public_jwks(
        private_key_file=new_private,
        signing_kid="kid-new",
        output_file=output,
        merge_existing_file=output,
        replace=True,
    )

    assert [key["kid"] for key in rotated["keys"]] == [
        "kid-new",
        "kid-old",
    ]
    assert all("d" not in key for key in rotated["keys"])


def test_rotation_rejects_conflicting_duplicate_kid(tmp_path: Path) -> None:
    first_private = tmp_path / "first.pem"
    second_private = tmp_path / "second.pem"
    existing = tmp_path / "existing.json"
    write_private_key(first_private)
    write_private_key(second_private)
    write_json(existing, public_jwks(first_private, "same-kid"))

    with pytest.raises(JarvisJwksExportError, match="conflicting duplicate kid"):
        build_rotation_jwks(
            public_jwks(second_private, "same-kid"),
            existing_public_jwks_file=existing,
        )


def test_existing_jwks_rejects_private_material(tmp_path: Path) -> None:
    private_key = tmp_path / "private.pem"
    current_private = tmp_path / "current.pem"
    existing = tmp_path / "existing.json"
    write_private_key(private_key)
    write_private_key(current_private)

    leaked = public_jwks(private_key, "old-kid")
    leaked["keys"][0]["d"] = "forbidden-private-coordinate"  # type: ignore[index]
    write_json(existing, leaked)

    with pytest.raises(JarvisJwksExportError):
        build_rotation_jwks(
            public_jwks(current_private, "new-kid"),
            existing_public_jwks_file=existing,
        )


def test_rotation_key_count_is_bounded_to_core_verifier_capacity(
    tmp_path: Path,
) -> None:
    current_private = tmp_path / "current.pem"
    write_private_key(current_private)

    old_keys = []
    for index in range(MAX_JWKS_KEYS):
        key_path = tmp_path / f"old-{index}.pem"
        write_private_key(key_path)
        old_keys.extend(public_jwks(key_path, f"old-{index}")["keys"])

    existing = tmp_path / "existing.json"
    write_json(existing, {"keys": old_keys})

    with pytest.raises(JarvisJwksExportError, match="capacity"):
        build_rotation_jwks(
            public_jwks(current_private, "new-kid"),
            existing_public_jwks_file=existing,
        )


def test_public_output_must_not_overwrite_private_key(tmp_path: Path) -> None:
    private_key = tmp_path / "private.pem"
    write_private_key(private_key)

    with pytest.raises(JarvisJwksExportError):
        export_public_jwks(
            private_key_file=private_key,
            signing_kid="kid-v1",
            output_file=private_key,
            replace=True,
        )


def test_cli_never_prints_jwks_coordinates_or_private_material(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_key = tmp_path / "private.pem"
    output = tmp_path / "public.json"
    write_private_key(private_key)

    assert (
        main(
            [
                "--private-key-file",
                str(private_key),
                "--kid",
                "kid-v1",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    captured = capsys.readouterr().out
    jwks = json.loads(output.read_text(encoding="utf-8"))
    key = jwks["keys"][0]
    assert str(output) in captured
    assert "kid-v1" in captured
    assert key["x"] not in captured
    assert key["y"] not in captured
    assert "BEGIN PRIVATE KEY" not in captured
