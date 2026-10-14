"""Bot oqimlarini boshidan oxirigacha tekshiradi: haqiqiy Telegram o'rniga soxta sessiya,
haqiqiy handlerlar, middleware'lar, FSM va (SQLite) baza."""

import itertools
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    GetFile,
    SendMessage,
)
from aiogram.types import Chat, File, Message, Update
from sqlalchemy import select

from app.api.main import app
from app.bot.factory import create_dispatcher
from app.bot.handlers import get_routers
from app.config import Settings
from app.db.seed import seed_districts
from app.models import Complaint, ComplaintCategory, District, User

TG_ID = 42
_ids = itertools.count(1)


class FakeSession(BaseSession):
    """Telegram'ga chiqmaydi: yuborilgan so'rovlarni yozib boradi."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list = []
        self.edit_not_modified = False
        self.blocked_chats: set[int] = set()  # shu chatlarga yuborish "bot bloklangan" xatosini beradi

    async def close(self) -> None:
        pass

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b"fake-jpeg-bytes"

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if self.edit_not_modified and isinstance(method, EditMessageText):
            raise TelegramBadRequest(method=method, message="Bad Request: message is not modified")
        if isinstance(method, SendMessage) and method.chat_id in self.blocked_chats:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="u1", file_path="photos/f.jpg")
        return True


class Env:
    def __init__(self, dp, bot, fake, session_factory, tmp_path, provider):
        self.dp, self.bot, self.fake = dp, bot, fake
        self.session_factory, self.tmp_path, self.provider = session_factory, tmp_path, provider

    # --- yuborilgan narsalarni o'qish ---
    def sent(self) -> list[SendMessage]:
        return [r for r in self.fake.requests if isinstance(r, SendMessage)]

    def texts(self) -> list[str]:
        return [r.text for r in self.sent()]

    def last_text(self) -> str:
        return self.texts()[-1]

    def edits(self) -> list[EditMessageText]:
        return [r for r in self.fake.requests if isinstance(r, EditMessageText)]

    def toasts(self) -> list[AnswerCallbackQuery]:
        return [r for r in self.fake.requests if isinstance(r, AnswerCallbackQuery)]

    def clear(self) -> None:
        self.fake.requests.clear()

    # --- foydalanuvchi harakatlari ---
    def _message(self, **fields) -> dict:
        return {
            "message_id": next(_ids),
            "date": int(datetime.now(UTC).timestamp()),
            "chat": {"id": TG_ID, "type": "private"},
            "from": {"id": TG_ID, "is_bot": False, "first_name": "Test", "language_code": "uz"},
            **fields,
        }

    async def feed(self, update: dict) -> None:
        parsed = Update.model_validate({"update_id": next(_ids), **update}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, parsed)

    async def say(self, text: str) -> None:
        fields: dict = {"text": text}
        if text.startswith("/"):
            fields["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        await self.feed({"message": self._message(**fields)})

    async def send_location(self, lat: float, lon: float) -> None:
        await self.feed({"message": self._message(location={"latitude": lat, "longitude": lon})})

    async def send_photo(self, file_id: str = "PHOTO1") -> None:
        photo = [{"file_id": file_id, "file_unique_id": "u", "width": 90, "height": 90}]
        await self.feed({"message": self._message(photo=photo)})

    async def press(self, data: str) -> None:
        callback = {
            "id": str(next(_ids)),
            "from": {"id": TG_ID, "is_bot": False, "first_name": "Test", "language_code": "uz"},
            "chat_instance": "ci",
            "data": data,
            "message": self._message(text="eski xabar"),
        }
        await self.feed({"callback_query": callback})

    # --- baza va holat ---
    async def user(self) -> User | None:
        async with self.session_factory() as s:
            return await s.scalar(select(User).where(User.telegram_id == TG_ID))

    async def district(self, slug: str) -> District:
        async with self.session_factory() as s:
            return await s.scalar(select(District).where(District.slug == slug))

    async def complaints(self) -> list[Complaint]:
        async with self.session_factory() as s:
            return list((await s.scalars(select(Complaint))).all())

    async def fsm_state(self) -> str | None:
        key = StorageKey(bot_id=self.bot.id, chat_id=TG_ID, user_id=TG_ID)
        return await self.dp.storage.get_state(key)

    async def onboard(self, slug: str = "chilonzor", lang: str = "uz") -> None:
        """Foydalanuvchini bazada tayyor holatda yaratadi (til + hudud tanlangan)."""
        district = await self.district(slug)
        async with self.session_factory() as s:
            s.add(User(telegram_id=TG_ID, language=lang, district_id=district.id))
            await s.commit()


@pytest_asyncio.fixture
async def env(session_factory, provider, tmp_path):
    async with session_factory() as s:
        await seed_districts(s)
    settings = Settings(bot_token="", media_dir=str(tmp_path / "media"), max_complaints_per_day=5)
    # Routerlar modul darajasida yaratilgan va faqat bitta Dispatcher'ga ulanadi. Ishlab
    # chiqarishda jarayonda bitta Dispatcher bor; testlarda har safar yangisini yig'amiz.
    for router in get_routers():
        router._parent_router = None
    dp = create_dispatcher(
        redis=None,
        provider=provider,
        settings=settings,
        session_factory=session_factory,
        storage=MemoryStorage(),
    )
    fake = FakeSession()
    bot = Bot("123456:TEST-TOKEN", session=fake)
    return Env(dp, bot, fake, session_factory, tmp_path, provider)


# --- Onboarding --------------------------------------------------------------


async def test_start_creates_user_and_asks_language(env):
    await env.say("/start")
    user = await env.user()
    assert user is not None and user.language == "uz" and user.district_id is None
    assert "Выберите язык" in env.last_text()
    markup = env.sent()[-1].reply_markup
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["lang:uz", "lang:ru", "lang:en"]


async def test_full_onboarding_in_russian(env):
    await env.say("/start")
    await env.press("lang:ru")
    assert (await env.user()).language == "ru"
    assert "Здравствуйте" in env.texts()[-2] and "геолокацию" in env.last_text()

    chilonzor = await env.district("chilonzor")
    await env.send_location(chilonzor.lat + 0.002, chilonzor.lon)
    user = await env.user()
    assert user.district_id == chilonzor.id
    assert "Район определён" in env.last_text() and "Чиланзар" in env.last_text()

    # Menyu tugmasi tilga mos kelishi kerak
    await env.say("🌫 Качество воздуха")
    assert "AQI: <b>132</b>" in env.last_text() and "Чиланзар" in env.last_text()
    assert env.provider.calls == 1


async def test_full_onboarding_in_english(env):
    await env.say("/start")
    await env.press("lang:en")
    assert (await env.user()).language == "en"
    assert "Hello" in env.texts()[-2] and "location" in env.last_text().lower()

    chilonzor = await env.district("chilonzor")
    await env.send_location(chilonzor.lat + 0.002, chilonzor.lon)
    user = await env.user()
    assert user.district_id == chilonzor.id
    assert "District detected" in env.last_text() and "Chilanzar" in env.last_text()

    # Menyu tugmasi tilga mos kelishi kerak
    await env.say("🌫 Air quality")
    assert "AQI: <b>132</b>" in env.last_text() and "Chilanzar" in env.last_text()
    assert env.provider.calls == 1


async def test_location_outside_uzbekistan_falls_back_to_list(env):
    await env.say("/start")
    await env.press("lang:uz")
    await env.send_location(55.75, 37.62)  # Moskva
    assert (await env.user()).district_id is None
    assert "topilmadi" in env.texts()[-2]
    first_row = env.sent()[-1].reply_markup.inline_keyboard[0]
    assert first_row[0].callback_data.startswith("dist:set:")


async def test_pick_district_from_list_and_regions(env):
    await env.say("/start")
    await env.press("lang:uz")
    await env.say("🏙 Ro'yxatdan tanlash")
    markup = env.sent()[-1].reply_markup
    all_buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(all_buttons) == 12 + 1  # 12 tuman + "Boshqa hudud"
    assert all_buttons[-1].callback_data == "dist:list:set:regions"

    await env.press("dist:list:set:regions")
    markup_edits = [r for r in env.fake.requests if isinstance(r, EditMessageReplyMarkup)]
    region_buttons = [b for row in markup_edits[-1].reply_markup.inline_keyboard for b in row]
    assert len(region_buttons) == 13 + 1  # 13 viloyat + "Toshkent shahri"ga qaytish
    assert region_buttons[-1].callback_data == "dist:list:set:city"

    samarkand = await env.district("samarqand")
    await env.press(f"dist:set:{samarkand.id}")
    assert (await env.user()).district_id == samarkand.id
    assert "Samarqand viloyati" in env.last_text()


# --- Havo sifati -------------------------------------------------------------


async def test_air_without_district_asks_to_choose(env):
    await env.say("/start")
    await env.say("🌫 Havo sifati")
    assert "hududingizni tanlang" in env.last_text()
    assert env.provider.calls == 0


async def test_air_message_and_cache(env):
    await env.onboard()
    await env.say("🌫 Havo sifati")
    text = env.last_text()
    assert "Chilonzor" in text and "🟠" in text and "Zararli" in text and "16:30" in text
    assert "PM2.5: 48.0" in text and "niqob" in text

    await env.say("🌫 Havo sifati")  # ikkinchi marta: bazadagi o'lchov, provayder qayta chaqirilmaydi
    assert env.provider.calls == 1


async def test_air_provider_down_shows_friendly_message(env):
    await env.onboard()
    env.provider.fail = True
    await env.say("🌫 Havo sifati")
    assert "olib bo'lmadi" in env.last_text()


async def test_refresh_not_modified_gives_toast(env):
    await env.onboard()
    district = await env.district("chilonzor")
    env.fake.edit_not_modified = True
    await env.press(f"air:refresh:{district.id}")
    assert any(toast.text == "Ma'lumot hali yangilanmagan" for toast in env.toasts())


async def test_view_other_district_does_not_change_saved_one(env):
    await env.onboard("chilonzor")
    sergeli = await env.district("sergeli")
    await env.press(f"dist:view:{sergeli.id}")
    assert "Sergeli" in env.edits()[-1].text
    assert (await env.user()).district_id == (await env.district("chilonzor")).id


# --- Ogohlantirish sozlamalari -----------------------------------------------


async def test_toggle_settings(env):
    await env.onboard()
    await env.press("set:digest")
    await env.press("set:alert")
    user = await env.user()
    assert user.daily_digest is True and user.alert_enabled is False


async def test_toggle_requires_district(env):
    await env.say("/start")
    await env.press("set:digest")
    assert (await env.user()).daily_digest is False
    assert any(toast.show_alert for toast in env.toasts())


# --- Murojaat (FSM) ----------------------------------------------------------


async def _walk_to_text_step(env) -> None:
    await env.say("📝 Murojaat yuborish")
    await env.press("cat:burning")
    await env.send_photo("PHOTO1")
    await env.send_location(41.2751, 69.2041)


async def test_complaint_happy_path(env):
    await env.onboard("chilonzor")
    await env.say("📝 Murojaat yuborish")
    assert await env.fsm_state() == "ComplaintForm:category"
    await env.press("cat:burning")
    assert await env.fsm_state() == "ComplaintForm:photo"
    await env.send_photo("PHOTO1")
    assert await env.fsm_state() == "ComplaintForm:location"
    await env.send_location(41.2751, 69.2041)
    assert await env.fsm_state() == "ComplaintForm:text"
    await env.say("Qo'shni hovlida <chiqindi> yoqilmoqda")
    assert await env.fsm_state() == "ComplaintForm:confirm"

    summary = env.last_text()
    assert "Chilonzor" in summary and "bor" in summary
    assert "&lt;chiqindi&gt;" in summary  # foydalanuvchi matni HTML'dan himoyalangan

    await env.press("cmp:confirm")
    assert await env.fsm_state() is None
    assert "№1" in env.last_text()

    (complaint,) = await env.complaints()
    chilonzor = await env.district("chilonzor")
    assert complaint.category is ComplaintCategory.BURNING
    assert complaint.status.value == "new"
    assert complaint.district_id == chilonzor.id
    assert (complaint.lat, complaint.lon) == (41.2751, 69.2041)
    assert complaint.location_is_approx is False
    assert complaint.text == "Qo'shni hovlida <chiqindi> yoqilmoqda"
    assert complaint.photo_file_id == "PHOTO1"
    saved = Path(env.tmp_path / "media" / complaint.photo_path)
    assert saved.read_bytes() == b"fake-jpeg-bytes"


async def test_complaint_without_photo_using_district_center(env):
    await env.onboard("sergeli")
    await env.say("📝 Murojaat yuborish")
    await env.press("cat:industrial")
    await env.press("cmp:skip_photo")
    await env.say("📍 Hududim markazidan foydalanish")
    await env.say("Zavod tutuni juda ko'p")
    assert "taxminiy" in env.last_text() and "yo'q" in env.last_text()
    await env.press("cmp:confirm")

    (complaint,) = await env.complaints()
    sergeli = await env.district("sergeli")
    assert complaint.location_is_approx is True
    assert (complaint.lat, complaint.lon) == (sergeli.lat, sergeli.lon)
    assert complaint.photo_file_id is None and complaint.photo_path is None


async def test_double_confirm_creates_single_complaint(env):
    await env.onboard()
    await _walk_to_text_step(env)
    await env.say("Tutun va hid bor, nafas olish qiyin")
    await env.press("cmp:confirm")
    await env.press("cmp:confirm")  # ikkinchi bosish
    assert len(await env.complaints()) == 1


async def test_complaint_text_validation(env):
    await env.onboard()
    await _walk_to_text_step(env)
    await env.say("ab")
    assert "5 dan 1000" in env.last_text()
    assert await env.fsm_state() == "ComplaintForm:text"
    await env.say("x" * 1001)
    assert await env.fsm_state() == "ComplaintForm:text"
    assert await env.complaints() == []


async def test_wrong_input_in_steps_is_rejected_politely(env):
    await env.onboard()
    await env.say("📝 Murojaat yuborish")
    await env.press("cat:other")
    await env.say("rasm o'rniga matn")
    assert "rasm yuboring" in env.last_text() and await env.fsm_state() == "ComplaintForm:photo"
    await env.press("cmp:skip_photo")
    await env.say("lokatsiya o'rniga matn")
    assert "joylashuv yuboring" in env.last_text() and await env.fsm_state() == "ComplaintForm:location"


async def test_menu_button_during_complaint_is_not_saved_as_text(env):
    await env.onboard()
    await _walk_to_text_step(env)
    await env.say("🌫 Havo sifati")
    assert "AQI" in env.last_text()
    assert await env.fsm_state() is None
    assert await env.complaints() == []


async def test_cancel_by_command_and_button(env):
    await env.onboard()
    await env.say("📝 Murojaat yuborish")
    await env.say("/cancel")
    assert env.last_text() == "Bekor qilindi." and await env.fsm_state() is None

    await env.say("📝 Murojaat yuborish")
    await env.press("cmp:cancel")
    assert env.last_text() == "Bekor qilindi." and await env.fsm_state() is None


async def test_daily_limit(env):
    await env.onboard()
    user = await env.user()
    async with env.session_factory() as s:
        for _ in range(5):
            s.add(
                Complaint(
                    user_id=user.id,
                    category=ComplaintCategory.OTHER,
                    lat=41.3,
                    lon=69.2,
                    text="oldingi murojaat",
                )
            )
        await s.commit()

    await env.say("📝 Murojaat yuborish")
    assert "5 ta murojaat" in env.last_text()
    assert await env.fsm_state() is None


async def test_stale_callback_is_acknowledged(env):
    await env.onboard()
    await env.press("cmp:confirm")  # holat yo'q: eski tugma
    assert env.toasts() and await env.complaints() == []


async def test_unknown_text_shows_menu_hint(env):
    await env.onboard()
    await env.say("salom qalaysiz")
    assert "menyudan foydalaning" in env.last_text()


async def test_blocked_user_is_reactivated_on_return(env):
    await env.onboard()
    async with env.session_factory() as s:
        user = await s.scalar(select(User))
        user.is_active = False
        await s.commit()
    await env.say("salom")
    assert (await env.user()).is_active is True


# --- Webhook -----------------------------------------------------------------


async def test_webhook_endpoint(env):
    app.state.settings = Settings(bot_token="", bot_mode="webhook", webhook_secret="s3cret")
    app.state.bot, app.state.dp = env.bot, env.dp
    update = {"update_id": 1, "message": env._message(text="/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}])}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post("/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        missing = await client.post("/telegram/webhook", json=update)
        ok = await client.post("/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})

        app.state.settings = Settings(bot_token="", bot_mode="polling")
        disabled = await client.post("/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
        health = await client.get("/health")

    assert (bad.status_code, missing.status_code, ok.status_code) == (403, 403, 200)
    assert disabled.status_code == 404
    assert health.json() == {"status": "ok"}
    assert "Выберите язык" in env.last_text()
