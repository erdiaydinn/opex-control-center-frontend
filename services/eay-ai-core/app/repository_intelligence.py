from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

ALLOWED_CLASSIFICATIONS = frozenset({"OWN", "IMPORTED", "DISCOVERED"})
ALLOWED_DECISIONS = frozenset({"ADOPT", "WATCH", "REFERENCE", "REJECT", "PENDING"})
ALLOWED_IDENTITY_STATUS = frozenset({"VERIFIED", "UNRESOLVED"})

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "repository_intelligence_registry.json"

REQUIRED_SEED_IDS = frozenset(
    {
        "own-opex-control-center-frontend",
        "own-planai-audit",
        "own-adaronya",
        "imported-council-of-high-intelligence",
        "imported-cl4r1t4s",
        "imported-computer-lab-automation",
        "imported-deep-learning-tutorials",
        "imported-impeccable",
        "imported-image-understanding-tthau",
        "imported-jarvis-erdi-full-start",
        "imported-jarvis-erdi-starter-patch",
        "imported-jarvis-main-family",
        "imported-jarvis-master",
        "discovered-apache-superset",
        "discovered-patika-superset-tr",
        "discovered-llama-cpp",
        "discovered-ollama",
        "discovered-langgraph",
        "discovered-pending-local-llm-serving-routing",
        "discovered-pending-agent-rag-eval-observability",
        "discovered-pending-vision-doc-ml-lifecycle",
        "discovered-pending-workflow-security-finetuning",
    }
)

EXCLUDED_PATH_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "__pycache__",
        ".next",
        ".turbo",
        ".vite",
    }
)
EXCLUDED_FILENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
    }
)
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


class RepositoryRegistryError(ValueError):
    pass


class RegistryFingerprint(str):
    """String fingerprint that remains callable for the frozen v0.1 API contract."""

    def __call__(self) -> str:
        return str(self)


@dataclass(frozen=True)
class RepositoryReviewView:
    ref: str | None
    commit: str | None
    license: str
    commercial_use: str


class RepositoryEntryView(Mapping[str, Any]):
    """Read-only adapter exposing both v0.1 attribute and v0.2 mapping contracts."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def __getitem__(self, key: str) -> Any:
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)

    @property
    def id(self) -> str:
        return self._payload["id"]

    @property
    def identity(self) -> str | None:
        return self._payload["repository"]

    @property
    def canonical_upstream(self) -> str | None:
        return self._payload["canonical_upstream"]

    @property
    def classification(self) -> str:
        return self._payload["classification"]

    @property
    def decision(self) -> str:
        return self._payload["decision"]

    @property
    def review(self) -> RepositoryReviewView:
        license_info = self._payload["license"]
        license_name = license_info.get("spdx") or "unresolved"
        commercial_use = (
            "blocked"
            if self._payload["identity_status"] == "UNRESOLVED"
            or self._payload["decision"] in {"REJECT", "PENDING"}
            else "reviewed"
        )
        return RepositoryReviewView(
            ref=self._payload["last_reviewed_ref"],
            commit=self._payload["last_reviewed_sha"],
            license=license_name,
            commercial_use=commercial_use,
        )


@dataclass(frozen=True)
class RepositoryRegistry:
    schema_version: int
    updated_at: str
    entries: tuple[dict[str, Any], ...]
    fingerprint: RegistryFingerprint

    def by_id(self, entry_id: str | None = None) -> RepositoryEntryView | dict[str, RepositoryEntryView]:
        views = {entry["id"]: RepositoryEntryView(entry) for entry in self.entries}
        if entry_id is None:
            return views
        try:
            return views[entry_id]
        except KeyError:
            raise KeyError(entry_id) from None

    @property
    def repositories(self) -> tuple[RepositoryEntryView, ...]:
        return tuple(RepositoryEntryView(entry) for entry in self.entries)

    @property
    def unresolved(self) -> tuple[dict[str, Any], ...]:
        return tuple(entry for entry in self.entries if entry["identity_status"] == "UNRESOLVED")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def registry_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _validate_entry(entry: dict[str, Any]) -> None:
    required = {
        "id",
        "classification",
        "display_name",
        "repository",
        "source_locator",
        "canonical_upstream",
        "relation",
        "last_reviewed_ref",
        "last_reviewed_sha",
        "license",
        "capabilities",
        "decision",
        "identity_status",
    }
    missing = required - entry.keys()
    if missing:
        raise RepositoryRegistryError(f"registry entry {entry.get('id')!r} missing fields: {sorted(missing)}")

    if entry["classification"] not in ALLOWED_CLASSIFICATIONS:
        raise RepositoryRegistryError(f"invalid classification for {entry['id']}")
    if entry["decision"] not in ALLOWED_DECISIONS:
        raise RepositoryRegistryError(f"invalid decision for {entry['id']}")
    if entry["identity_status"] not in ALLOWED_IDENTITY_STATUS:
        raise RepositoryRegistryError(f"invalid identity status for {entry['id']}")

    repository = entry["repository"]
    if entry["identity_status"] == "VERIFIED":
        if not isinstance(repository, str) or repository.count("/") != 1:
            raise RepositoryRegistryError(f"verified entry {entry['id']} requires exact owner/repo identity")
    elif repository is not None:
        raise RepositoryRegistryError(
            f"unresolved entry {entry['id']} must keep repository=null rather than inventing owner/repo"
        )

    reviewed_sha = entry["last_reviewed_sha"]
    if reviewed_sha is not None:
        if not isinstance(reviewed_sha, str) or len(reviewed_sha) != 40 or any(
            char not in "0123456789abcdef" for char in reviewed_sha.lower()
        ):
            raise RepositoryRegistryError(f"invalid reviewed commit SHA for {entry['id']}")
        if not entry["last_reviewed_ref"]:
            raise RepositoryRegistryError(f"reviewed SHA without branch/tag/ref for {entry['id']}")

    license_info = entry["license"]
    if not isinstance(license_info, dict) or set(license_info) != {"spdx", "status"}:
        raise RepositoryRegistryError(f"invalid license contract for {entry['id']}")
    if entry["classification"] != "OWN" and entry["decision"] == "ADOPT" and license_info["status"] != "VERIFIED":
        raise RepositoryRegistryError(f"external code cannot be adopted before license verification: {entry['id']}")

    if not isinstance(entry["capabilities"], list) or not entry["capabilities"]:
        raise RepositoryRegistryError(f"capability mapping required for {entry['id']}")


def _parse_repository_registry_payload(payload: Any) -> RepositoryRegistry:
    if not isinstance(payload, dict):
        raise RepositoryRegistryError("repository registry must be a JSON object")
    if payload.get("schema_version") != 1:
        raise RepositoryRegistryError("unsupported repository registry schema_version")
    if not isinstance(payload.get("updated_at"), str) or not payload["updated_at"]:
        raise RepositoryRegistryError("registry updated_at is required")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RepositoryRegistryError("registry entries must be a non-empty list")

    ids: set[str] = set()
    verified_repositories: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RepositoryRegistryError("registry entries must be objects")
        _validate_entry(entry)
        entry_id = entry["id"]
        if entry_id in ids:
            raise RepositoryRegistryError(f"duplicate registry id: {entry_id}")
        ids.add(entry_id)

        if entry["identity_status"] == "VERIFIED":
            repository_key = entry["repository"].casefold()
            existing_entry_id = verified_repositories.get(repository_key)
            if existing_entry_id is not None:
                raise RepositoryRegistryError(
                    "verified repository identity cannot be duplicated across registry entries: "
                    f"{existing_entry_id}, {entry_id}"
                )
            verified_repositories[repository_key] = entry_id

    missing_seeds = REQUIRED_SEED_IDS - ids
    if missing_seeds:
        raise RepositoryRegistryError(f"canonical seed entries may not be silently dropped: {sorted(missing_seeds)}")

    return RepositoryRegistry(
        schema_version=payload["schema_version"],
        updated_at=payload["updated_at"],
        entries=tuple(entries),
        fingerprint=RegistryFingerprint(registry_fingerprint(payload)),
    )


def load_repository_registry_text(source_text: str) -> RepositoryRegistry:
    """Load a registry from already-verified UTF-8 text without weakening validation."""
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise RepositoryRegistryError("repository registry is not valid JSON") from exc
    return _parse_repository_registry_payload(payload)


def load_repository_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> RepositoryRegistry:
    registry_path = Path(path)
    return load_repository_registry_text(registry_path.read_text(encoding="utf-8"))


def should_index_repository_path(path: str) -> bool:
    """Return False for secrets, generated/vendor noise, and private-key material."""
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    parts = normalized.split("/")
    lowered_parts = {part.lower() for part in parts}
    if lowered_parts & {part.lower() for part in EXCLUDED_PATH_PARTS}:
        return False

    filename = parts[-1].lower()
    if filename in EXCLUDED_FILENAMES or filename.startswith(".env."):
        return False
    if filename.endswith(SECRET_SUFFIXES):
        return False
    if "private" in filename and "key" in filename:
        return False
    return True
