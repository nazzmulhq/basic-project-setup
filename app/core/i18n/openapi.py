import copy
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from starlette.responses import HTMLResponse

from app.core.i18n.config import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.core.i18n.locales import CATALOGS

_OPENAPI_CACHE: dict[str, dict[str, Any]] = {}


def clear_openapi_cache() -> None:
    _OPENAPI_CACHE.clear()


def get_localized_openapi(app: FastAPI, lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    """Generate or fetch cached OpenAPI schema translated to the requested language."""
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    if lang in _OPENAPI_CACHE:
        return _OPENAPI_CACHE[lang]

    catalog = CATALOGS.get(lang, CATALOGS[DEFAULT_LANGUAGE])
    swagger_meta = catalog.get("swagger", {})

    # Build base localized tags metadata
    tags_metadata: list[dict[str, str]] = []
    for tag_name, tag_desc in swagger_meta.get("tags", {}).items():
        tags_metadata.append({"name": tag_name, "description": tag_desc})

    # Generate initial OpenAPI schema
    schema = get_openapi(
        title=swagger_meta.get("title", app.title),
        version=app.version,
        openapi_version=app.openapi_version,
        description=swagger_meta.get("description", app.description),
        routes=app.routes,
        tags=tags_metadata,
        servers=app.servers,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info,
    )
    schema = copy.deepcopy(schema)

    # Localize route paths, summaries, descriptions, responses, and parameters
    routes_meta = swagger_meta.get("routes", {})
    common_params = swagger_meta.get("common_parameters", {})
    common_responses = swagger_meta.get("common_responses", {})

    paths = schema.get("paths", {})
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                continue
            if not isinstance(operation, dict):
                continue

            route_meta = routes_meta.get((path, method.lower()))
            if route_meta:
                if "summary" in route_meta:
                    operation["summary"] = route_meta["summary"]
                if "description" in route_meta:
                    operation["description"] = route_meta["description"]

                # Localize response descriptions
                if "responses" in route_meta:
                    op_responses = operation.setdefault("responses", {})
                    for status_code, resp_desc in route_meta["responses"].items():
                        if status_code in op_responses:
                            op_responses[status_code]["description"] = resp_desc
                        else:
                            op_responses[status_code] = {"description": resp_desc}

                # Localize parameter descriptions
                if "parameters" in route_meta and "parameters" in operation:
                    for param in operation["parameters"]:
                        p_name = param.get("name")
                        if p_name in route_meta["parameters"]:
                            param["description"] = route_meta["parameters"][p_name]

            # Common fallback translations for parameters
            if "parameters" in operation:
                for param in operation["parameters"]:
                    p_name = param.get("name")
                    if (
                        not param.get("description")
                        or param.get("description").startswith("The ")
                        or p_name in ("limit", "offset", "q", "user_id")
                    ) and p_name in common_params:
                        param["description"] = common_params[p_name]

            # Common fallback translations for responses
            if "responses" in operation:
                for status_code, resp_obj in operation["responses"].items():
                    if isinstance(resp_obj, dict):
                        curr_desc = resp_obj.get("description", "")
                        if (
                            curr_desc in ("Successful Response", "Validation Error", "")
                            and status_code in common_responses
                        ):
                            resp_obj["description"] = common_responses[status_code]

    _OPENAPI_CACHE[lang] = schema
    return schema


def render_localized_swagger_ui(
    openapi_url: str,
    title: str,
    current_lang: str = DEFAULT_LANGUAGE,
) -> HTMLResponse:
    """Render Swagger UI HTML with an integrated language selector banner."""
    base_response = get_swagger_ui_html(
        openapi_url=openapi_url,
        title=title,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )
    html_content = bytes(base_response.body).decode("utf-8")

    en_active = (
        "background: #3b82f6; color: #ffffff; border: 1px solid #60a5fa;"
        if current_lang == "en"
        else "background: #334155; color: #cbd5e1; border: 1px solid #475569;"
    )
    bn_active = (
        "background: #3b82f6; color: #ffffff; border: 1px solid #60a5fa;"
        if current_lang == "bn"
        else "background: #334155; color: #cbd5e1; border: 1px solid #475569;"
    )

    banner_html = f"""
    <div id="i18n-language-switcher" style="
        background: #0f172a;
        color: #f8fafc;
        padding: 12px 28px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid #2563eb;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
    ">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.3rem;">🌐</span>
            <span style="font-weight: 600; font-size: 0.95rem; letter-spacing: 0.3px;">
                Documentation Language / ডকুমেন্টেশনের ভাষা:
            </span>
        </div>
        <div style="display: flex; gap: 12px;">
            <a href="/docs?lang=en" style="
                padding: 6px 16px;
                border-radius: 6px;
                text-decoration: none;
                font-size: 0.88rem;
                font-weight: 600;
                transition: all 0.2s;
                {en_active}
            ">🇬🇧 English</a>
            <a href="/docs?lang=bn" style="
                padding: 6px 16px;
                border-radius: 6px;
                text-decoration: none;
                font-size: 0.88rem;
                font-weight: 600;
                transition: all 0.2s;
                {bn_active}
            ">🇧🇩 বাংলা (Bengali)</a>
        </div>
    </div>
    """

    if '<div id="swagger-ui">' in html_content:
        html_content = html_content.replace(
            '<div id="swagger-ui">',
            f'{banner_html}\n    <div id="swagger-ui">',
        )

    return HTMLResponse(content=html_content)


def render_localized_redoc(
    openapi_url: str,
    title: str,
    current_lang: str = DEFAULT_LANGUAGE,
) -> HTMLResponse:
    """Render ReDoc HTML with an integrated language selector banner."""
    base_response = get_redoc_html(
        openapi_url=openapi_url,
        title=title,
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )
    html_content = bytes(base_response.body).decode("utf-8")

    en_active = (
        "background: #3b82f6; color: #ffffff; border: 1px solid #60a5fa;"
        if current_lang == "en"
        else "background: #334155; color: #cbd5e1; border: 1px solid #475569;"
    )
    bn_active = (
        "background: #3b82f6; color: #ffffff; border: 1px solid #60a5fa;"
        if current_lang == "bn"
        else "background: #334155; color: #cbd5e1; border: 1px solid #475569;"
    )

    btn_base = (
        "padding: 6px 16px; border-radius: 6px; text-decoration: none; "
        "font-size: 0.88rem; font-weight: 600; "
    )

    banner_html = f"""
    <div id="i18n-language-switcher" style="
        background: #0f172a;
        color: #f8fafc;
        padding: 12px 28px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid #2563eb;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    ">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.3rem;">🌐</span>
            <span style="font-weight: 600; font-size: 0.95rem;">Language / ভাষা:</span>
        </div>
        <div style="display: flex; gap: 12px;">
            <a href="/redoc?lang=en" style="{btn_base}{en_active}">🇬🇧 English</a>
            <a href="/redoc?lang=bn" style="{btn_base}{bn_active}">🇧🇩 বাংলা (Bengali)</a>
        </div>
    </div>
    """

    if "<body>" in html_content:
        html_content = html_content.replace(
            "<body>",
            f"<body>\n    {banner_html}",
        )

    return HTMLResponse(content=html_content)
