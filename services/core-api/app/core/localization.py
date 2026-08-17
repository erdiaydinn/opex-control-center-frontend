from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_LOCALES: tuple[str, ...] = (
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
SUPPORTED_LOCALE_SET = frozenset(SUPPORTED_LOCALES)
DEFAULT_LOCALE = "en"
RTL_LOCALES = frozenset({"ar"})

_LOCALE_CANONICAL = {locale.casefold(): locale for locale in SUPPORTED_LOCALES}


@dataclass(frozen=True)
class LocaleContext:
    locale: str
    rtl: bool
    source: str


def canonicalize_locale(value: str | None) -> str | None:
    """Return one platform-supported canonical locale or None.

    Locale labels are presentation context, never tenant/security authority.  The
    supported set is nevertheless centralized so individual modules cannot
    silently diverge from the platform's language contract.
    """
    raw = str(value or "").strip()
    if not raw:
        return None

    direct = _LOCALE_CANONICAL.get(raw.casefold())
    if direct is not None:
        return direct

    # Accept a regional browser tag only when its base language is explicitly
    # supported.  pt-BR remains canonical rather than being collapsed to pt.
    base = raw.split("-", 1)[0].casefold()
    return _LOCALE_CANONICAL.get(base)


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
    return LocaleContext(locale=locale, rtl=locale in RTL_LOCALES, source="accept-language" if candidates else "default")
