import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.core.i18n import (
    I18nMiddleware,
    get_current_language,
    get_localized_openapi,
    render_localized_redoc,
    render_localized_swagger_ui,
    resolve_language,
    t,
)
from app.core.migration_runner import run_auto_migrations
from app.core.redis_cluster import RedisClusterClient, init_redis_cluster
from app.core.session import AsyncSessionLocal, engine
from app.core.tantivy_search import (
    TantivyUserIndex,
    close_tantivy_user_index,
    init_tantivy_user_index,
)
from app.db.seeder import run_initial_seed
from app.workers.outbox_relay import OutboxRelayWorker

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_client: RedisClusterClient | None = None
    search_index: TantivyUserIndex | None = None
    worker: OutboxRelayWorker | None = None
    try:
        await run_auto_migrations()
        redis_client = await init_redis_cluster()
        search_index = init_tantivy_user_index()
        async with AsyncSessionLocal() as session:
            await run_initial_seed(session, search_index)
        worker = OutboxRelayWorker(search_index)
        await worker.recover_and_flush_on_startup()
        worker.start()
        logger.info("Application startup complete; Tantivy outbox relay is active")
        yield
    finally:
        if worker is not None:
            await worker.stop()
        if search_index is not None:
            await close_tantivy_user_index()
        if redis_client is not None:
            await redis_client.aclose()
        await engine.dispose()


app = FastAPI(
    title="FastAPI Enterprise Architecture Blueprint",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(I18nMiddleware)

# Delegate default openapi generation to current language schema for full backwards compatibility
app.openapi = lambda: get_localized_openapi(app, get_current_language())  # type: ignore[method-assign]


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str):
        detail = t(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    # Translate custom error messages if present
    translated_errors = []
    for err in errors:
        msg = err.get("msg", "")
        err_copy = dict(err)
        err_copy["msg"] = t(msg)
        translated_errors.append(err_copy)
    return JSONResponse(
        status_code=422,
        content={"detail": translated_errors},
    )


@app.get("/openapi.json", include_in_schema=False)
async def openapi_endpoint(
    request: Request,
    lang: str | None = Query(default=None),
) -> JSONResponse:
    target_lang = resolve_language(lang, request.headers.get("accept-language"))
    schema = get_localized_openapi(app, target_lang)
    return JSONResponse(schema)


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html(
    request: Request,
    lang: str | None = Query(default=None),
) -> HTMLResponse:
    target_lang = resolve_language(lang, request.headers.get("accept-language"))
    return render_localized_swagger_ui(
        openapi_url=f"/openapi.json?lang={target_lang}",
        title=f"{app.title} - Swagger UI",
        current_lang=target_lang,
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html(
    request: Request,
    lang: str | None = Query(default=None),
) -> HTMLResponse:
    target_lang = resolve_language(lang, request.headers.get("accept-language"))
    return render_localized_redoc(
        openapi_url=f"/openapi.json?lang={target_lang}",
        title=f"{app.title} - ReDoc",
        current_lang=target_lang,
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/health", tags=["Health"], summary="Health Check")
async def health() -> dict[str, str]:
    return {"status": t("ok")}
