from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

_EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)
_TR_PHONE_RE = re.compile(r"(?<!\d)(?:\+?90[\s.-]?)?(?:0[\s.-]?)?5\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}(?!\d)")
_TR_IBAN_RE = re.compile(r"(?<![A-Z0-9])TR(?:[\s-]?\d){24}(?![A-Z0-9])", re.IGNORECASE)
_DIGIT_RUN_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")


@dataclass(frozen=True)
class PrivacyFinding:
    kind: str
    token_sha256: str


@dataclass(frozen=True)
class PrivacyScanResult:
    safe: bool
    findings: tuple[PrivacyFinding, ...]

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({item.kind for item in self.findings}))


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digits(value: str) -> str:
    return "".join(char for char in value if char.isdigit())


def is_valid_tckn(value: str) -> bool:
    """Validate an 11-digit Turkish identity number without retaining the number.

    The checksum gate intentionally reduces false positives versus flagging every
    arbitrary 11-digit operational identifier. Numbers beginning with zero are invalid.
    """

    if len(value) != 11 or not value.isdigit() or value[0] == "0":
        return False
    digits = [int(char) for char in value]
    odd_sum = sum(digits[index] for index in (0, 2, 4, 6, 8))
    even_sum = sum(digits[index] for index in (1, 3, 5, 7))
    if ((odd_sum * 7) - even_sum) % 10 != digits[9]:
        return False
    return sum(digits[:10]) % 10 == digits[10]


def scan_personal_data(texts: Iterable[object]) -> PrivacyScanResult:
    """Detect high-confidence personal-data patterns for training fail-closed gates.

    Raw matched values are never returned. Only finding type and SHA-256 token hashes
    leave this function, keeping auditability without copying personal data into logs.
    """

    findings: list[PrivacyFinding] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, token: str) -> None:
        normalized = token.strip().casefold()
        key = (kind, _token_hash(normalized))
        if key in seen:
            return
        seen.add(key)
        findings.append(PrivacyFinding(kind=kind, token_sha256=key[1]))

    for raw in texts:
        text = str(raw or "")
        if not text:
            continue
        for match in _EMAIL_RE.finditer(text):
            add("email", match.group(0))
        for match in _TR_PHONE_RE.finditer(text):
            digits = _digits(match.group(0))
            if len(digits) in {10, 11, 12}:
                add("turkish_phone", digits)
        for match in _TR_IBAN_RE.finditer(text):
            digits = _digits(match.group(0))
            if len(digits) == 24:
                add("turkish_iban", "TR" + digits)
        for match in _DIGIT_RUN_RE.finditer(text):
            candidate = match.group(0)
            if is_valid_tckn(candidate):
                add("tckn", candidate)

    findings.sort(key=lambda item: (item.kind, item.token_sha256))
    return PrivacyScanResult(safe=not findings, findings=tuple(findings))
