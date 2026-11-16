from app.core.i18n.locales.bn import bn_catalog
from app.core.i18n.locales.en import en_catalog

CATALOGS: dict[str, dict] = {
    "en": en_catalog,
    "bn": bn_catalog,
}

__all__ = ["CATALOGS", "en_catalog", "bn_catalog"]
