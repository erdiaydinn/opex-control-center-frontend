from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field, HttpUrl, model_validator


DEFAULT_CONSUMER_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "tr_consumer_legal_registry.json"
)

_DISCOVERY_HOST_SUFFIX = "ticaret.gov.tr"
_BINDING_VERIFICATION_HOSTS = frozenset(
    {
        "resmigazete.gov.tr",
        "www.resmigazete.gov.tr",
        "mevzuat.gov.tr",
        "www.mevzuat.gov.tr",
    }
)


def _normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip().casefold()


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _is_discovery_host(host: str) -> bool:
    return host == _DISCOVERY_HOST_SUFFIX or host.endswith("." + _DISCOVERY_HOST_SUFFIX)


def is_binding_verification_host(url: str) -> bool:
    """Return whether URL is on the existing exact-source legal verification host set.

    Host eligibility alone never establishes binding authority; the existing legal verification
    path must still validate exact instrument text, publication/effective dates and human review.
    """

    return _hostname(url) in _BINDING_VERIFICATION_HOSTS


def _is_allowed_discovery_target(host: str) -> bool:
    return _is_discovery_host(host) or host in _BINDING_VERIFICATION_HOSTS


def _context_matches_title(context: str, title: str) -> bool:
    context_normalized = _normalized_text(context)
    context_normalized = re.sub(r"[\s|:;–—-]+$", "", context_normalized)
    return context_normalized.endswith(_normalized_text(title))


class ConsumerRegistryInstrument(BaseModel):
    key: str = Field(min_length=3, max_length=120)
    title: str = Field(min_length=5, max_length=300)
    law_number: str | None = Field(default=None, max_length=32)
    registry_target_url: HttpUrl
    topics: list[str] = Field(min_length=1)
    binding_source_required: Literal[True] = True

    @model_validator(mode="after")
    def exact_official_registry_target(self):
        host = _hostname(str(self.registry_target_url))
        if not _is_allowed_discovery_target(host):
            raise ValueError("consumer_registry_target_requires_official_host")
        return self


class ConsumerRegistryManifest(BaseModel):
    schema_version: Literal[1]
    observed_at: str = Field(min_length=10, max_length=40)
    registry_url: HttpUrl
    registry_role: Literal["official_registry_discovery"]
    instruments: list[ConsumerRegistryInstrument] = Field(min_length=1)

    @model_validator(mode="after")
    def fail_closed_registry_contract(self):
        if not _is_discovery_host(_hostname(str(self.registry_url))):
            raise ValueError("consumer_registry_requires_exact_ticaret_gov_tr_host")

        keys = [item.key.casefold() for item in self.instruments]
        titles = [_normalized_text(item.title) for item in self.instruments]
        targets = [str(item.registry_target_url) for item in self.instruments]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_consumer_registry_key")
        if len(titles) != len(set(titles)):
            raise ValueError("duplicate_consumer_registry_title")
        if len(targets) != len(set(targets)):
            raise ValueError("duplicate_consumer_registry_target")
        return self

    @property
    def manifest_fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class RegistryDiscoveryCandidate(BaseModel):
    instrument_key: str
    title: str
    registry_url: str
    registry_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_registry_target_url: str
    discovered_url: str
    discovered_host: str
    registry_target_match: Literal[True] = True
    discovery_only: Literal[True] = True
    binding_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False
    requires_exact_binding_source: Literal[True] = True

    @property
    def discovered_url_is_binding_host(self) -> bool:
        return is_binding_verification_host(self.discovered_url)


class _AnchorParser(HTMLParser):
    """Collect anchors with nearby visible text so registry rows like TITLE | INDIR resolve."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self._context_before_anchor = ""
        self._recent_visible: list[str] = []
        self.anchors: list[tuple[str, str, str]] = []

    def _remember(self, data: str) -> None:
        if data.strip():
            self._recent_visible.append(data)
            self._recent_visible = self._recent_visible[-16:]

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.lower() != "a":
            return
        href = next((value for key, value in attrs if key.lower() == "href"), None)
        self._href = str(href) if href else None
        self._parts = []
        self._context_before_anchor = " ".join(self._recent_visible)

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)
        else:
            self._remember(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        label = " ".join(self._parts).strip()
        self.anchors.append((label, self._href, self._context_before_anchor))
        if label:
            self._remember(label)
        self._href = None
        self._parts = []
        self._context_before_anchor = ""


def load_consumer_registry_manifest(
    path: Path = DEFAULT_CONSUMER_REGISTRY_PATH,
) -> ConsumerRegistryManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ConsumerRegistryManifest.model_validate(payload)


def _safe_discovered_url(registry_url: str, href: str) -> str:
    resolved = urljoin(registry_url, href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("consumer_registry_discovered_url_requires_http_https")
    if parsed.username or parsed.password:
        raise ValueError("consumer_registry_discovered_url_must_not_contain_userinfo")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("consumer_registry_discovered_url_requires_host")
    if not _is_allowed_discovery_target(host):
        raise ValueError("consumer_registry_discovered_url_requires_official_target_host")
    return resolved


def resolve_priority_registry_links(
    html: str,
    manifest: ConsumerRegistryManifest,
) -> tuple[RegistryDiscoveryCandidate, ...]:
    """Resolve configured titles from an already-fetched official registry page.

    This is deliberately a discovery-only parser. It does not fetch arbitrary URLs, does not
    classify discovered content as binding law, and cannot construct a promotion-eligible object.
    A change in the Ministry registry's target URL fails closed for review rather than silently
    rebinding a known instrument to a different document.
    """

    parser = _AnchorParser()
    parser.feed(html)

    manifest_fingerprint = manifest.manifest_fingerprint
    resolved: list[RegistryDiscoveryCandidate] = []
    for instrument in manifest.instruments:
        title_normalized = _normalized_text(instrument.title)
        matches: list[str] = []
        for label, href, context in parser.anchors:
            if _normalized_text(label) == title_normalized or _context_matches_title(
                context, instrument.title
            ):
                matches.append(href)

        if len(matches) > 1:
            raise ValueError(f"ambiguous_consumer_registry_title:{instrument.key}")
        if not matches:
            continue

        discovered_url = _safe_discovered_url(str(manifest.registry_url), matches[0])
        expected_url = str(instrument.registry_target_url)
        if discovered_url != expected_url:
            raise ValueError(f"consumer_registry_target_drift:{instrument.key}")

        resolved.append(
            RegistryDiscoveryCandidate(
                instrument_key=instrument.key,
                title=instrument.title,
                registry_url=str(manifest.registry_url),
                registry_manifest_fingerprint=manifest_fingerprint,
                expected_registry_target_url=expected_url,
                discovered_url=discovered_url,
                discovered_host=_hostname(discovered_url),
            )
        )

    return tuple(resolved)
