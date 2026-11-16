from typing import Final

SUPPORTED_LANGUAGES: Final[dict[str, str]] = {
    "en": "English",
    "bn": "বাংলা",
}

DEFAULT_LANGUAGE: Final[str] = "en"


def normalize_language_code(code: str) -> str:
    """Normalize language code e.g. 'bn-BD', 'bn_IN', 'BN' -> 'bn'."""
    clean = code.strip().lower().replace("_", "-")
    primary = clean.split("-")[0]
    return primary if primary in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def parse_accept_language(header: str | None) -> str:
    """Parse Accept-Language header considering quality values (e.g. 'bn-BD,bn;q=0.9,en;q=0.8')."""
    if not header:
        return DEFAULT_LANGUAGE

    languages: list[tuple[str, float]] = []
    for piece in header.split(","):
        parts = piece.strip().split(";")
        if not parts or not parts[0]:
            continue
        lang = parts[0].strip().lower().replace("_", "-").split("-")[0]
        q = 1.0
        for param in parts[1:]:
            param_parts = param.strip().split("=")
            if len(param_parts) == 2 and param_parts[0].strip() == "q":
                try:
                    q = float(param_parts[1].strip())
                except ValueError:
                    q = 0.0
        if lang in SUPPORTED_LANGUAGES:
            languages.append((lang, q))

    if not languages:
        return DEFAULT_LANGUAGE

    languages.sort(key=lambda item: item[1], reverse=True)
    return languages[0][0]


def resolve_language(
    query_lang: str | None = None, accept_language_header: str | None = None
) -> str:
    """Resolve target language from query parameter, Accept-Language header, or fallback."""
    if query_lang:
        normalized = query_lang.strip().lower().replace("_", "-").split("-")[0]
        if normalized in SUPPORTED_LANGUAGES:
            return normalized

    if accept_language_header:
        parsed = parse_accept_language(accept_language_header)
        if parsed in SUPPORTED_LANGUAGES:
            return parsed

    return DEFAULT_LANGUAGE
