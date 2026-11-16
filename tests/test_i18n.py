import pytest
from httpx import ASGITransport, AsyncClient

from app.core.i18n import (
    get_localized_openapi,
    resolve_language,
    t,
)
from app.main import app


def test_language_resolution() -> None:
    assert resolve_language(query_lang="bn") == "bn"
    assert resolve_language(query_lang="en") == "en"
    assert resolve_language(query_lang="fr") == "en"  # fallback

    assert resolve_language(accept_language_header="bn-BD,bn;q=0.9,en;q=0.8") == "bn"
    assert resolve_language(accept_language_header="en-US,en;q=0.9") == "en"
    assert resolve_language(accept_language_header="de,fr;q=0.5") == "en"  # fallback
    assert resolve_language() == "en"


def test_translation_messages() -> None:
    # Direct lookup
    assert t("Invalid email or password", lang="en") == "Invalid email or password"
    assert t("Invalid email or password", lang="bn") == "ভুল ইমেল বা পাসওয়ার্ড"
    assert t("User not found", lang="bn") == "ব্যবহারকারী খুঁজে পাওয়া যায়নি"

    # Dynamic pattern replacement
    bn_perm = t("Missing required permissions: ['users:read']", lang="bn")
    assert "প্রয়োজনীয় অনুমতির অভাব" in bn_perm
    assert "['users:read']" in bn_perm

    # Fallback for unknown text
    assert t("Unknown string", lang="bn") == "Unknown string"


def test_openapi_schema_localization() -> None:
    schema_en = get_localized_openapi(app, "en")
    schema_bn = get_localized_openapi(app, "bn")

    # Titles
    assert schema_en["info"]["title"] == "FastAPI Enterprise Architecture Blueprint"
    assert schema_bn["info"]["title"] == "ফাস্টএপিআই এন্টারপ্রাইজ আর্কিটেকচার ব্লুপ্রিন্ট"

    # Route summaries in English
    paths_en = schema_en["paths"]
    assert paths_en["/health"]["get"]["summary"] == "Health Check"
    assert paths_en["/api/v1/auth/login"]["post"]["summary"] == "User Login"
    assert paths_en["/api/v1/auth/refresh"]["post"]["summary"] == "Refresh Access Token"
    assert paths_en["/api/v1/auth/logout"]["post"]["summary"] == "User Logout"
    assert paths_en["/api/v1/auth/me"]["get"]["summary"] == "Current User Principal"
    assert paths_en["/api/v1/users"]["get"]["summary"] == "List Users (Paginated)"
    assert paths_en["/api/v1/users"]["post"]["summary"] == "Create User"
    assert paths_en["/api/v1/users/search"]["get"]["summary"] == "Search Users"
    assert paths_en["/api/v1/users/{user_id}/roles"]["put"]["summary"] == "Update User Roles"
    assert paths_en["/api/v1/users/{user_id}"]["delete"]["summary"] == "Deactivate User"

    # Route summaries in Bengali
    paths_bn = schema_bn["paths"]
    assert paths_bn["/health"]["get"]["summary"] == "স্বাস্থ্য পরীক্ষা"
    assert paths_bn["/api/v1/auth/login"]["post"]["summary"] == "ব্যবহারকারী লগইন"
    assert paths_bn["/api/v1/auth/refresh"]["post"]["summary"] == "টোকেন রিফ্রেশ"
    assert paths_bn["/api/v1/auth/logout"]["post"]["summary"] == "ব্যবহারকারী লগআউট"
    assert paths_bn["/api/v1/auth/me"]["get"]["summary"] == "বর্তমান ব্যবহারকারীর তথ্য"
    assert paths_bn["/api/v1/users"]["get"]["summary"] == "ব্যবহারকারীদের তালিকা (পৃষ্ঠাভিত্তিক)"
    assert paths_bn["/api/v1/users"]["post"]["summary"] == "নতুন ব্যবহারকারী তৈরি"
    assert paths_bn["/api/v1/users/search"]["get"]["summary"] == "ব্যবহারকারী অনুসন্ধান"
    assert paths_bn["/api/v1/users/{user_id}/roles"]["put"]["summary"] == "ব্যবহারকারীর রোল পরিবর্তন"
    assert paths_bn["/api/v1/users/{user_id}"]["delete"]["summary"] == "ব্যবহারকারী নিষ্ক্রিয়করণ"

    # Tags metadata in Bengali
    bn_tags = {tag["name"]: tag["description"] for tag in schema_bn["tags"]}
    assert "প্রমাণীকরণ" in bn_tags["Authentication"] or "টোকেন" in bn_tags["Authentication"]
    assert "ব্যবস্থাপনা" in bn_tags["Users & RBAC"] or "অনুসন্ধান" in bn_tags["Users & RBAC"]


@pytest.mark.asyncio
async def test_swagger_and_openapi_endpoints() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. OpenAPI JSON with ?lang=bn
        res_bn = await client.get("/openapi.json?lang=bn")
        assert res_bn.status_code == 200
        data_bn = res_bn.json()
        assert data_bn["info"]["title"] == "ফাস্টএপিআই এন্টারপ্রাইজ আর্কিটেকচার ব্লুপ্রিন্ট"
        assert data_bn["paths"]["/health"]["get"]["summary"] == "স্বাস্থ্য পরীক্ষা"
        assert res_bn.headers["Content-Language"] == "bn"

        # 2. OpenAPI JSON with Accept-Language header
        res_header = await client.get(
            "/openapi.json", headers={"Accept-Language": "bn-BD,bn;q=0.9"}
        )
        assert res_header.status_code == 200
        assert res_header.json()["info"]["title"] == "ফাস্টএপিআই এন্টারপ্রাইজ আর্কিটেকচার ব্লুপ্রিন্ট"

        # 3. OpenAPI JSON with ?lang=en
        res_en = await client.get("/openapi.json?lang=en")
        assert res_en.status_code == 200
        data_en = res_en.json()
        assert data_en["info"]["title"] == "FastAPI Enterprise Architecture Blueprint"
        assert data_en["paths"]["/health"]["get"]["summary"] == "Health Check"
        assert res_en.headers["Content-Language"] == "en"

        # 4. Swagger UI HTML
        res_docs_en = await client.get("/docs?lang=en")
        assert res_docs_en.status_code == 200
        assert "Documentation Language / ডকুমেন্টেশনের ভাষা" in res_docs_en.text
        assert "openapi.json?lang=en" in res_docs_en.text

        res_docs_bn = await client.get("/docs?lang=bn")
        assert res_docs_bn.status_code == 200
        assert "Documentation Language / ডকুমেন্টেশনের ভাষা" in res_docs_bn.text
        assert "openapi.json?lang=bn" in res_docs_bn.text

        # 5. Localized health endpoint
        res_health_en = await client.get("/health", headers={"Accept-Language": "en"})
        assert res_health_en.status_code == 200
        assert res_health_en.json() == {"status": "ok"}
        assert res_health_en.headers["Content-Language"] == "en"

        res_health_bn = await client.get("/health", headers={"Accept-Language": "bn"})
        assert res_health_bn.status_code == 200
        assert res_health_bn.json() == {"status": "সচল"}
        assert res_health_bn.headers["Content-Language"] == "bn"
