"""Juda oddiy i18n: kalit -> matn, til bo'yicha."""

from app.core.locales import en, ru, uz

LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

_TEXTS: dict[str, dict[str, str]] = {"uz": uz.TEXTS, "ru": ru.TEXTS, "en": en.TEXTS}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Matnni oladi. Tilda kalit bo'lmasa, o'zbekchasi ishlatiladi."""
    texts = _TEXTS.get(lang, _TEXTS[DEFAULT_LANG])
    template = texts.get(key)
    if template is None:
        template = _TEXTS[DEFAULT_LANG][key]
    return template.format(**kwargs)


def all_translations(key: str) -> set[str]:
    """Kalitning barcha tillardagi matni (tugma matnini tilga qaramay tanib olish uchun)."""
    return {texts[key] for texts in _TEXTS.values() if key in texts}
