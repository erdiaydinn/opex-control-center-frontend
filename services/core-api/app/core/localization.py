from __future__ import annotations

from dataclasses import dataclass

# Product UI release contract. These locales require critical-key completeness,
# UI QA and accessibility acceptance before they can be advertised as supported
# application languages.
UI_RELEASE_LOCALES: tuple[str, ...] = (
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

# Backward-compatible names used by existing UI and Accept-Language consumers.
# Keep these UI-only: adding an Academy content language must never silently make
# the complete EAY application claim that language as production-translated.
SUPPORTED_LOCALES = UI_RELEASE_LOCALES
SUPPORTED_LOCALE_SET = frozenset(SUPPORTED_LOCALES)

# Academy / knowledge / evidence contract. A locale in this tier may be used for
# authored content, quizzes, captions, transcripts and grounded source evidence.
# It does NOT imply that the full EAY UI has completed linguistic QA in that locale.
EXTENDED_CONTENT_LOCALES: tuple[str, ...] = (
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
CONTENT_LOCALES: tuple[str, ...] = UI_RELEASE_LOCALES + EXTENDED_CONTENT_LOCALES
CONTENT_LOCALE_SET = frozenset(CONTENT_LOCALES)

DEFAULT_LOCALE = "en"
RTL_LOCALES = frozenset({"ar"})
CONTENT_RTL_LOCALES = frozenset({"ar", "fa", "ur", "ckb", "he", "ps"})

_UI_CANONICAL = {locale.casefold(): locale for locale in UI_RELEASE_LOCALES}
_CONTENT_CANONICAL = {locale.casefold(): locale for locale in CONTENT_LOCALES}
_CONTENT_ALIASES = {
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
    "pt-br": "pt-BR",
    "pt-pt": "pt-PT",
    "fa-ir": "fa",
    "ru-ru": "ru",
    "ro-ro": "ro",
    "bs-ba": "bs-Latn",
    "bs-latn-ba": "bs-Latn",
    "sq-al": "sq",
    "ka-ge": "ka",
    "ku-tr": "ku-Latn",
    "ku-latn-tr": "ku-Latn",
    "ckb-iq": "ckb",
    "bg-bg": "bg",
    "hy-am": "hy",
    "zh-cn": "zh-Hans",
    "zh-sg": "zh-Hans",
    "zh-hans": "zh-Hans",
    "zh-hans-cn": "zh-Hans",
    "sr-latn": "sr-Latn",
    "sr-latn-rs": "sr-Latn",
    "mk-mk": "mk",
    "id-id": "id",
    "hu-hu": "hu",
    "az-az": "az",
    "uk-ua": "uk",
    "el-gr": "el",
    "ms-my": "ms",
    "uz-latn": "uz-Latn",
    "uz-latn-uz": "uz-Latn",
    "hi-in": "hi",
    "ur-pk": "ur",
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

# Region-only tags may collapse to a canonical language only when the platform
# does not maintain multiple canonical variants for that language. Script-sensitive
# languages are handled through explicit aliases above instead of guessing.
_CONTENT_REGION_COLLAPSIBLE = frozenset(
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


@dataclass(frozen=True)
class LocaleContext:
    locale: str
    rtl: bool
    source: str


def _clean_locale(value: str | None) -> str:
    return str(value or "").strip().replace("_", "-")


def canonicalize_locale(value: str | None) -> str | None:
    """Return one UI-release locale or None.

    Locale labels are presentation context, never tenant/security authority. The
    UI set stays intentionally narrow so content-language expansion cannot make
    the application silently advertise unverified UI translations.
    """
    raw = _clean_locale(value)
    if not raw:
        return None

    direct = _UI_CANONICAL.get(raw.casefold())
    if direct is not None:
        return direct

    # Accept a regional browser tag only when its base language is explicitly
    # UI-supported. pt-BR remains canonical rather than being collapsed to pt.
    base = raw.split("-", 1)[0].casefold()
    return _UI_CANONICAL.get(base)


def canonicalize_content_locale(value: str | None) -> str | None:
    """Return one Academy/content/evidence locale or None.

    This is deliberately broader than canonicalize_locale(). Script-sensitive
    aliases are explicit so we never guess Serbian, Chinese, Kurdish or Uzbek
    script variants from an ambiguous bare regional tag.
    """
    raw = _clean_locale(value)
    if not raw:
        return None

    folded = raw.casefold()
    direct = _CONTENT_CANONICAL.get(folded)
    if direct is not None:
        return direct

    alias = _CONTENT_ALIASES.get(folded)
    if alias is not None:
        return alias

    base = folded.split("-", 1)[0]
    if base in _CONTENT_REGION_COLLAPSIBLE:
        return _CONTENT_CANONICAL.get(base)
    return None


def content_direction(locale: str) -> str:
    canonical = canonicalize_content_locale(locale)
    if canonical is None:
        raise ValueError("locale must be part of the EAY content locale contract")
    return "rtl" if canonical in CONTENT_RTL_LOCALES else "ltr"


def resolve_accept_language(value: str | None, *, default: str = DEFAULT_LOCALE) -> LocaleContext:
    default_locale = canonicalize_locale(default)
    if default_locale is None:
        raise ValueError("default locale must be part of the EAY platform locale contract")

    candidates: list[tuple[float, int, str]] = []
    for index, part in enumerate(str(value or "").split(",")):
        token = part.strip()
        if not token:
            continue
        language, *parameters = token.split(";")
        quality = 1.0
        for parameter in parameters:
            name, separator, raw_value = parameter.strip().partition("=")
            if separator and name.casefold() == "q":
                try:
                    quality = float(raw_value)
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        locale = canonicalize_locale(language)
        if locale is not None:
            candidates.append((quality, -index, locale))

    locale = max(candidates)[2] if candidates else default_locale
    return LocaleContext(
        locale=locale,
        rtl=locale in RTL_LOCALES,
        source="accept-language" if candidates else "default",
    )
