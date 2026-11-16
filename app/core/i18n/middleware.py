from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.i18n.config import resolve_language
from app.core.i18n.context import set_current_language


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        query_lang = request.query_params.get("lang") or request.query_params.get("locale")
        accept_header = request.headers.get("accept-language")

        active_lang = resolve_language(query_lang, accept_header)
        set_current_language(active_lang)

        response = await call_next(request)
        response.headers["Content-Language"] = active_lang
        return response
