from typing import Any

from app.core.i18n.config import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.core.i18n.context import get_current_language
from app.core.i18n.locales import CATALOGS


def _resolve_nested_key(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def translate(key_or_text: str, lang: str | None = None, **kwargs: Any) -> str:
    """
    Translate a string or dot-notated key into the target language.
    Falls back to English if the translation is missing.
    Supports variable interpolation via format kwargs (e.g. {permissions}).
    """
    selected_lang = lang or get_current_language()
    if selected_lang not in SUPPORTED_LANGUAGES:
        selected_lang = DEFAULT_LANGUAGE

    catalog = CATALOGS.get(selected_lang, CATALOGS[DEFAULT_LANGUAGE])
    default_catalog = CATALOGS[DEFAULT_LANGUAGE]

    # 1. Direct message dictionary lookup
    result = catalog.get("messages", {}).get(key_or_text)

    # 1b. Dynamic pattern matching for permissions and roles
    if result is None:
        if key_or_text.startswith("Missing required permissions: "):
            perms = key_or_text[len("Missing required permissions: ") :]
            pattern = catalog.get("messages", {}).get(
                "Missing required permissions: {permissions}",
                "Missing required permissions: {permissions}",
            )
            return pattern.format(permissions=perms)
        if key_or_text.startswith("Required one of roles: "):
            roles = key_or_text[len("Required one of roles: ") :]
            pattern = catalog.get("messages", {}).get(
                "Required one of roles: {roles}",
                "Required one of roles: {roles}",
            )
            return pattern.format(roles=roles)

    # 2. Nested key path lookup (e.g. 'swagger.title')
    if result is None and "." in key_or_text:
        result = _resolve_nested_key(catalog, key_or_text)

    # 3. Fallback to default catalog (English)
    if result is None:
        result = default_catalog.get("messages", {}).get(key_or_text)
    if result is None and "." in key_or_text:
        result = _resolve_nested_key(default_catalog, key_or_text)

    # 4. If still not found, return key_or_text as-is
    if result is None or not isinstance(result, str):
        result = key_or_text

    # 5. Format placeholders if kwargs are provided
    if kwargs:
        try:
            return result.format(**kwargs)
        except (KeyError, ValueError):
            return result

    return result


t = translate
