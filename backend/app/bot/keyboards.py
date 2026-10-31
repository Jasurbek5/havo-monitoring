"""Barcha klaviaturalar. Matnlar til fayllaridan olinadi."""

from collections.abc import Iterable, Sequence
from typing import TypeVar

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.i18n import t
from app.models import ComplaintCategory, District, User

T = TypeVar("T")


def _chunk(items: Sequence[T], size: int) -> list[list[T]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _inline(rows: Iterable[Iterable[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows])


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


# --- Reply klaviaturalar ----------------------------------------------------


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_air")), KeyboardButton(text=t(lang, "btn_weather"))],
            [KeyboardButton(text=t(lang, "btn_complaint")), KeyboardButton(text=t(lang, "btn_district"))],
            [KeyboardButton(text=t(lang, "btn_alerts")), KeyboardButton(text=t(lang, "btn_language"))],
        ],
        resize_keyboard=True,
    )


def district_prompt_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_send_location"), request_location=True)],
            [
                KeyboardButton(text=t(lang, "btn_search_city")),
                KeyboardButton(text=t(lang, "btn_choose_list")),
            ],
            [KeyboardButton(text=t(lang, "btn_cancel"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def search_results_kb(
    results: Sequence[tuple[int, str]], lang: str
) -> InlineKeyboardMarkup:
    """Qidiruv natijalarini tanlash uchun inline tugmalar (index bo'yicha)."""
    rows = [[_btn(f"📍 {name}", f"loc:pick:{idx}")] for idx, name in results]
    rows.append([_btn(t(lang, "btn_cancel"), "loc:cancel")])
    return _inline(rows)


def complaint_location_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_send_location"), request_location=True)],
            [KeyboardButton(text=t(lang, "btn_use_my_district"))],
            [KeyboardButton(text=t(lang, "btn_cancel"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# --- Inline klaviaturalar ---------------------------------------------------


def language_kb() -> InlineKeyboardMarkup:
    return _inline(
        [
            [_btn("🇺🇿 O'zbekcha", "lang:uz"), _btn("🇷🇺 Русский", "lang:ru")],
            [_btn("🇬🇧 English", "lang:en")],
        ]
    )


def districts_kb(
    districts: Sequence[District], lang: str, *, mode: str, group: str
) -> InlineKeyboardMarkup:
    """Hududlar ro'yxati.

    mode:  "set"  - foydalanuvchining hududini o'zgartirish,
           "view" - boshqa hudud havosini faqat ko'rish.
    group: "city" - Toshkent tumanlari, "regions" - viloyatlar.
    """
    buttons = [_btn(d.name(lang), f"dist:{mode}:{d.id}") for d in districts]
    rows = _chunk(buttons, 2 if group == "city" else 1)
    if group == "city":
        rows.append([_btn(t(lang, "btn_other_region"), f"dist:list:{mode}:regions")])
    else:
        rows.append([_btn(t(lang, "btn_back_city"), f"dist:list:{mode}:city")])
    return _inline(rows)


def air_kb(
    lang: str,
    district_id: int,
    *,
    switch_district: District | None = None,
    is_home: bool = False,
    web_app_url: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_btn(t(lang, "btn_today_weather"), f"weather:today:{district_id}")],
    ]
    if web_app_url:
        label = "📱 Mini App (Interaktiv)" if lang == "uz" else ("📱 Mini App (Интерактив)" if lang == "ru" else "📱 Mini App (Interactive)")
        rows.append([InlineKeyboardButton(text=label, web_app=WebAppInfo(url=f"{web_app_url}?district_id={district_id}&lang={lang}"))])
    if switch_district is not None:
        switch_label = (
            t(lang, "btn_switch_to_other", name=switch_district.name(lang))
            if is_home
            else t(lang, "btn_switch_to_home", name=switch_district.name(lang))
        )
        rows.append(
            [
                _btn(t(lang, "btn_refresh"), f"air:refresh:{district_id}"),
                _btn(switch_label, f"air:switch:{switch_district.id}"),
            ]
        )
        rows.append([_btn(t(lang, "btn_all_districts"), "air:other")])
    else:
        rows.append(
            [
                _btn(t(lang, "btn_refresh"), f"air:refresh:{district_id}"),
                _btn(t(lang, "btn_other_district"), "air:other"),
            ]
        )
    return _inline(rows)


def today_weather_kb(
    lang: str,
    district_id: int,
    *,
    switch_district: District | None = None,
    is_home: bool = False,
    web_app_url: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_btn(t(lang, "btn_weekly_weather"), f"weather:week:{district_id}")],
    ]
    if web_app_url:
        label = "📱 Mini App (Interaktiv)" if lang == "uz" else ("📱 Mini App (Интерактив)" if lang == "ru" else "📱 Mini App (Interactive)")
        rows.append([InlineKeyboardButton(text=label, web_app=WebAppInfo(url=f"{web_app_url}?district_id={district_id}&lang={lang}"))])
    rows.append(
        [
            _btn(t(lang, "btn_back_to_air"), f"air:refresh:{district_id}"),
            _btn(t(lang, "btn_refresh"), f"weather:today:{district_id}"),
        ]
    )
    if switch_district is not None:
        switch_label = (
            t(lang, "btn_switch_to_other", name=switch_district.name(lang))
            if is_home
            else t(lang, "btn_switch_to_home", name=switch_district.name(lang))
        )
        rows.append(
            [
                _btn(switch_label, f"weather:today:{switch_district.id}"),
                _btn(t(lang, "btn_all_districts"), "air:other"),
            ]
        )
    else:
        rows.append([_btn(t(lang, "btn_other_district"), "air:other")])
    return _inline(rows)


def weekly_weather_kb(
    lang: str,
    district_id: int,
    *,
    switch_district: District | None = None,
    is_home: bool = False,
    web_app_url: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_btn(t(lang, "btn_back_to_today"), f"weather:today:{district_id}")],
    ]
    if web_app_url:
        label = "📱 Mini App (Interaktiv)" if lang == "uz" else ("📱 Mini App (Интерактив)" if lang == "ru" else "📱 Mini App (Interactive)")
        rows.append([InlineKeyboardButton(text=label, web_app=WebAppInfo(url=f"{web_app_url}?district_id={district_id}&lang={lang}"))])
    rows.append(
        [
            _btn(t(lang, "btn_back_to_air"), f"air:refresh:{district_id}"),
            _btn(t(lang, "btn_refresh"), f"weather:week:{district_id}"),
        ]
    )
    if switch_district is not None:
        switch_label = (
            t(lang, "btn_switch_to_other", name=switch_district.name(lang))
            if is_home
            else t(lang, "btn_switch_to_home", name=switch_district.name(lang))
        )
        rows.append([_btn(switch_label, f"weather:week:{switch_district.id}")])
    return _inline(rows)


TIMEZONE_OPTIONS = [
    ("auto", "tz_auto"),
    ("Asia/Tashkent", "tz_tashkent"),
    ("Europe/Moscow", "tz_moscow"),
    ("Asia/Tokyo", "tz_tokyo"),
    ("Asia/Dubai", "tz_dubai"),
    ("Asia/Almaty", "tz_almaty"),
    ("Europe/Istanbul", "tz_istanbul"),
    ("Europe/London", "tz_london"),
    ("America/New_York", "tz_new_york"),
    ("UTC", "tz_utc"),
]


def timezone_display_name(tz_val: str, lang: str) -> str:
    for code, key in TIMEZONE_OPTIONS:
        if code == tz_val:
            return t(lang, key)
    return tz_val or t(lang, "tz_auto")


def settings_kb(user: User, lang: str) -> InlineKeyboardMarkup:
    def state(flag: bool) -> str:
        return t(lang, "state_on" if flag else "state_off")

    home_name = user.home_district.name(lang) if user.home_district else "—"
    digest_time = user.digest_time or "07:00"
    user_tz = getattr(user, "timezone", "auto")
    tz_label = timezone_display_name(user_tz, lang)

    return _inline(
        [
            [_btn(t(lang, "toggle_alert", state=state(user.alert_enabled)), "set:alert")],
            [_btn(t(lang, "toggle_digest", state=state(user.daily_digest)), "set:digest")],
            [_btn(t(lang, "toggle_time", time=digest_time), "set:time")],
            [_btn(t(lang, "toggle_timezone", tz=tz_label), "set:tz")],
            [_btn(t(lang, "toggle_home", name=home_name), "set:home")],
        ]
    )


def timezone_kb(current_tz: str, lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for code, key in TIMEZONE_OPTIONS:
        mark = "✓ " if code == current_tz else ""
        buttons.append([_btn(f"{mark}{t(lang, key)}", f"tz:pick:{code}")])
    buttons.append([_btn(t(lang, "btn_back"), "set:back")])
    return _inline(buttons)


def digest_time_kb(current_time: str, lang: str) -> InlineKeyboardMarkup:
    times = ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00"]
    buttons = []
    for tm in times:
        mark = "✓ " if tm == current_time else ""
        buttons.append(_btn(f"{mark}{tm}", f"time:pick:{tm}"))
    rows = _chunk(buttons, 3)
    rows.append([_btn(t(lang, "btn_back"), "set:back")])
    return _inline(rows)


def home_settings_kb(user: User, lang: str) -> InlineKeyboardMarkup:
    rows = []
    if user.district and (not user.home_district or user.home_district_id != user.district_id):
        rows.append(
            [
                _btn(
                    t(lang, "btn_set_current_as_home", name=user.district.name(lang)),
                    "home:set_current",
                )
            ]
        )
    rows.append([_btn(t(lang, "btn_choose_from_list"), "home:choose_list")])
    if user.home_district_id:
        rows.append([_btn(t(lang, "btn_clear_home"), "home:clear")])
    rows.append([_btn(t(lang, "btn_back"), "set:back")])
    return _inline(rows)


def categories_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [[_btn(t(lang, f"cat_{c.value}"), f"cat:{c.value}")] for c in ComplaintCategory]
    rows.append([_btn(t(lang, "btn_cancel"), "cmp:cancel")])
    return _inline(rows)


def photo_kb(lang: str) -> InlineKeyboardMarkup:
    return _inline(
        [[_btn(t(lang, "btn_skip"), "cmp:skip_photo"), _btn(t(lang, "btn_cancel"), "cmp:cancel")]]
    )


def cancel_kb(lang: str) -> InlineKeyboardMarkup:
    return _inline([[_btn(t(lang, "btn_cancel"), "cmp:cancel")]])


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return _inline(
        [[_btn(t(lang, "btn_confirm"), "cmp:confirm"), _btn(t(lang, "btn_cancel"), "cmp:cancel")]]
    )
