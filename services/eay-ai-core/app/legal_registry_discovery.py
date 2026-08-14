from __future__ import annotations

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


class ConsumerRegistryInstrument(BaseModel):
    key: str = Field(min_length=3, max_length=120)
    title: str = Field(min_length=5, max_length=300)
    law_number: str | None = Field(default=None, max_length=32)
    topics: list[str] = Field(min_length=1)
    binding_source_required: Literal[True] = True


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
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_consumer_registry_key")
        if len(titles) != len(set(titles)):
            raise ValueError("duplicate_consumer_registry_title")
        return self


class RegistryDiscoveryCandidate(BaseModel):
    instrument_key: str
    title: str
    registry_url: str
    discovered_url: str
    discovered_host: str
    discovery_only: Literal[True] = True
    binding_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False
    requires_exact_binding_source: Literal[True] = True

    @property
    def discovered_url_is_binding_host(self) -> bool:
        return is_binding_verification_host(self.discovered_url)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.lower() != "a":
            return
        href = next((value for key, value in attrs if key.lower() == "href"), None)
        self._href = str(href) if href else None
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = " ".join(self._parts).strip()
        if title:
            self.anchors.append((title, self._href))
        self._href = None
        self._parts = []


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
    if not parsed.hostname:
        raise ValueError("consumer_registry_discovered_url_requires_host")
    return resolved


def resolve_priority_registry_links(
    html: str,
    manifest: ConsumerRegistryManifest,
) -> tuple[RegistryDiscoveryCandidate, ...]:
    """Resolve configured titles from an already-fetched official registry page.

    This is deliberately a discovery-only parser. It does not fetch arbitrary URLs, does not
    classify discovered content as binding law, and cannot construct a promotion-eligible object.
    """

    parser = _AnchorParser()
    parser.feed(html)

    anchors: dict[str, list[str]] = {}
    for visible_title, href in parser.anchors:
        anchors.setdefault(_normalized_text(visible_title), []).append(href)

    resolved: list[RegistryDiscoveryCandidate] = []
    for instrument in manifest.instruments:
        matches = anchors.get(_normalized_text(instrument.title), [])
        if len(matches) > 1:
            raise ValueError(f"ambiguous_consumer_registry_title:{instrument.key}")
        if not matches:
            continue
        discovered_url = _safe_discovered_url(str(manifest.registry_url), matches[0])
        resolved.append(
            RegistryDiscoveryCandidate(
                instrument_key=instrument.key,
                title=instrument.title,
                registry_url=str(manifest.registry_url),
                discovered_url=discovered_url,
                discovered_host=_hostname(discovered_url),
            )
        )

    return tuple(resolved)
