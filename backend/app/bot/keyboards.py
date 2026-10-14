"""Barcha klaviaturalar. Matnlar til fayllaridan olinadi."""

from collections.abc import Iterable, Sequence
from typing import TypeVar

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
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
            [KeyboardButton(text=t(lang, "btn_air")), KeyboardButton(text=t(lang, "btn_complaint"))],
            [KeyboardButton(text=t(lang, "btn_alerts")), KeyboardButton(text=t(lang, "btn_district"))],
            [KeyboardButton(text=t(lang, "btn_language"))],
        ],
        resize_keyboard=True,
    )


def district_prompt_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_send_location"), request_location=True)],
            [KeyboardButton(text=t(lang, "btn_choose_list"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


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


def air_kb(lang: str, district_id: int) -> InlineKeyboardMarkup:
    return _inline(
        [
            [
                _btn(t(lang, "btn_refresh"), f"air:refresh:{district_id}"),
                _btn(t(lang, "btn_other_district"), "air:other"),
            ]
        ]
    )


def settings_kb(user: User, lang: str) -> InlineKeyboardMarkup:
    def state(flag: bool) -> str:
        return t(lang, "state_on" if flag else "state_off")

    return _inline(
        [
            [_btn(t(lang, "toggle_alert", state=state(user.alert_enabled)), "set:alert")],
            [_btn(t(lang, "toggle_digest", state=state(user.daily_digest)), "set:digest")],
        ]
    )


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
