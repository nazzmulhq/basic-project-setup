from contextvars import ContextVar

from app.core.i18n.config import DEFAULT_LANGUAGE

_current_language_ctx: ContextVar[str] = ContextVar("current_language", default=DEFAULT_LANGUAGE)


def get_current_language() -> str:
    """Return the currently active language for this async execution context."""
    return _current_language_ctx.get()


def set_current_language(lang: str) -> None:
    """Set the active language for this async execution context."""
    _current_language_ctx.set(lang)
