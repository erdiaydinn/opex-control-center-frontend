from __future__ import annotations

from typing import Final

DEFAULT_LOCALE: Final = "tr"

# Platform release locales: UI translation completeness is a release gate for this tier.
CORE_RELEASE_LOCALES: Final[tuple[str, ...]] = (
    "tr",
    "en",
    "de",
    "ar",
    "fr",
    "es",
    "it",
    "nl",
    "pl",
    "pt-BR",
)

# Academy content/evidence locales. This tier is deliberately broader than the UI
# release tier so a tenant can author, ingest and retrieve training/SOP content in
# its operating language without pretending the full product UI is translated.
EXTENDED_CONTENT_LOCALES: Final[tuple[str, ...]] = (
    "fa",
    "ru",
    "ro",
    "bs-Latn",
    "sq",
    "ka",
    "ku-Latn",
    "ckb",
    "bg",
    "hy",
    "zh-Hans",
    "sr-Latn",
    "mk",
    "id",
    "hu",
    "az",
    "uk",
    "el",
    "ms",
    "uz-Latn",
    "hi",
    "ur",
    "pt-PT",
    "ja",
    "ko",
    "cs",
    "sk",
    "sv",
    "da",
    "no",
    "fi",
    "he",
    "th",
    "vi",
    "bn",
    "ps",
)

SUPPORTED_LOCALES: Final[tuple[str, ...]] = CORE_RELEASE_LOCALES + EXTENDED_CONTENT_LOCALES
SUPPORTED_LOCALE_SET: Final[frozenset[str]] = frozenset(SUPPORTED_LOCALES)

RTL_LOCALES: Final[frozenset[str]] = frozenset({"ar", "fa", "ur", "ckb", "he", "ps"})

# Backward-compatible and common regional aliases. Canonical Academy values stay
# compact where the platform already persisted compact values (tr/en/de/ar/etc.).
_LOCALE_ALIASES: Final[dict[str, str]] = {
    "tr-tr": "tr",
    "en-us": "en",
    "en-gb": "en",
    "de-de": "de",
    "ar-sa": "ar",
    "ar-eg": "ar",
    "fr-fr": "fr",
    "es-es": "es",
    "it-it": "it",
    "nl-nl": "nl",
    "pl-pl": "pl",
    "fa-ir": "fa",
    "ru-ru": "ru",
    "ro-ro": "ro",
    "bs-latn-ba": "bs-Latn",
    "sq-al": "sq",
    "ka-ge": "ka",
    "ku-tr": "ku-Latn",
    "ku-latn-tr": "ku-Latn",
    "ckb-iq": "ckb",
    "bg-bg": "bg",
    "hy-am": "hy",
    "zh-hans": "zh-Hans",
    "zh-cn": "zh-Hans",
    "sr-latn-rs": "sr-Latn",
    "mk-mk": "mk",
    "id-id": "id",
    "hu-hu": "hu",
    "az-az": "az",
    "uk-ua": "uk",
    "el-gr": "el",
    "ms-my": "ms",
    "uz-latn-uz": "uz-Latn",
    "hi-in": "hi",
    "ur-pk": "ur",
    "pt-br": "pt-BR",
    "pt-pt": "pt-PT",
    "ja-jp": "ja",
    "ko-kr": "ko",
    "cs-cz": "cs",
    "sk-sk": "sk",
    "sv-se": "sv",
    "da-dk": "da",
    "nb-no": "no",
    "no-no": "no",
    "fi-fi": "fi",
    "he-il": "he",
    "th-th": "th",
    "vi-vn": "vi",
    "bn-bd": "bn",
    "ps-af": "ps",
}

_CANONICAL_CASEFOLD: Final[dict[str, str]] = {
    locale.casefold(): locale for locale in SUPPORTED_LOCALES
}

# Languages where region-only variants can safely collapse to the existing
# language contract. Script-sensitive languages are intentionally excluded.
_REGION_COLLAPSIBLE: Final[frozenset[str]] = frozenset(
    {
        "tr",
        "en",
        "de",
        "ar",
        "fr",
        "es",
        "it",
        "nl",
        "pl",
        "fa",
        "ru",
        "ro",
        "sq",
        "ka",
        "ckb",
        "bg",
        "hy",
        "mk",
        "id",
        "hu",
        "az",
        "uk",
        "el",
        "ms",
        "hi",
        "ur",
        "ja",
        "ko",
        "cs",
        "sk",
        "sv",
        "da",
        "no",
        "fi",
        "he",
        "th",
        "vi",
        "bn",
        "ps",
    }
)


def normalize_locale(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Locale must be a string")

    cleaned = value.strip().replace("_", "-")
    if not cleaned:
        raise ValueError("Locale cannot be empty")

    folded = cleaned.casefold()
    if folded in _LOCALE_ALIASES:
        return _LOCALE_ALIASES[folded]
    if folded in _CANONICAL_CASEFOLD:
        return _CANONICAL_CASEFOLD[folded]

    language = folded.split("-", 1)[0]
    if language in _REGION_COLLAPSIBLE and language in SUPPORTED_LOCALE_SET:
        return language

    raise ValueError(f"Unsupported locale: {value}")


def normalize_i18n_map(value: dict[str, str], *, required: bool = True) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_locale, raw_text in value.items():
        locale = normalize_locale(raw_locale)
        if locale in normalized:
            raise ValueError(
                f"Duplicate locale after normalization: {raw_locale} resolves to {locale}"
            )
        if isinstance(raw_text, str) and raw_text.strip():
            normalized[locale] = raw_text.strip()

    if required and not normalized:
        raise ValueError("At least one non-empty localized value is required")
    return normalized


def direction_for_locale(locale: str) -> str:
    return "rtl" if normalize_locale(locale) in RTL_LOCALES else "ltr"


def metadata_fallback_chain(locale: str) -> tuple[str, ...]:
    """Metadata/UI fallback only; learning evidence never silently crosses locale."""
    requested = normalize_locale(locale)
    ordered = [requested]
    for fallback in ("en", DEFAULT_LOCALE):
        if fallback not in ordered:
            ordered.append(fallback)
    return tuple(ordered)


def localization_contract() -> dict[str, object]:
    return {
        "default_locale": DEFAULT_LOCALE,
        "core_release_locales": list(CORE_RELEASE_LOCALES),
        "extended_content_locales": list(EXTENDED_CONTENT_LOCALES),
        "supported_locales": list(SUPPORTED_LOCALES),
        "direction_by_locale": {
            locale: ("rtl" if locale in RTL_LOCALES else "ltr")
            for locale in SUPPORTED_LOCALES
        },
        "rtl_locales": sorted(RTL_LOCALES),
        "metadata_fallback_policy": "requested -> en -> tr",
        "learning_evidence_fallback_policy": "exact-locale-only",
        "ui_release_gate": "core-release-locales-require-complete-critical-keys",
    }
