# Havo sifati monitoringi va aholi murojaatlari tizimi

Toshkent tumanlari bo'yicha havo sifatini (AQI, PM2.5, PM10) kuzatadigan, aholiga Telegram bot orqali
holat va tavsiyalar yetkazadigan, havo ifloslanishi bo'yicha murojaatlarni qabul qiladigan tizim.

**Holat: 1-bosqich.** Backend, bot, baza, fon vazifalari va Docker tayyor. Admin dashboard (React) va
unga xizmat qiladigan admin API keyingi bosqichda (pastdagi "Keyingi qadamlar").

## Nima ishlaydi

**Bot** (aiogram 3, o'zbekcha, ruscha va inglizcha)
- `/start`: til tanlash, hudud tanlash (GPS yoki ro'yxat; Toshkentning 12 tumani + 13 viloyat markazi).
- Havo sifati: AQI, PM2.5, PM10, daraja (🟢 Yaxshi, 🟡 O'rtacha, 🟠 Zararli, 🔴 Xavfli) va tavsiyalar.
- Murojaat (FSM): tur, rasm, joylashuv, tavsif, tasdiqlash. Kuniga 5 ta cheklov (spamdan himoya).
- Ogohlantirishlar: AQI > 150 bo'lganda avtomatik xabar, ertalabki xabar (ixtiyoriy, 07:00).

**Backend**
- PostgreSQL: foydalanuvchilar, hududlar, havo tarixi, murojaatlar, adminlar (SQLAlchemy 2 + Alembic).
- Celery + Redis: har 30 daqiqada Toshkent tumanlari yangilanadi; viloyatlar faqat so'rov bo'yicha olinib keshlanadi.
- FastAPI: `/health`, `/health/ready`, Telegram webhook. Polling rejimida bot shu jarayon ichida ishlaydi.

## Papkalar strukturasi

```
havo-monitoring/
├── docker-compose.yml        db, redis, migrate, api, worker, beat (+ nginx: --profile prod)
├── .env.example
├── nginx/default.conf
└── backend/
    ├── Dockerfile, requirements*.txt, alembic.ini, pyproject.toml
    ├── requirements-lite.txt, .env.lite.example     yengil rejim (Docker'siz)
    ├── alembic/versions/0001_initial.py
    ├── app/
    │   ├── config.py                 sozlamalar (.env)
    │   ├── models/                   District, User, AirQualityLog, Complaint, AdminUser
    │   ├── db/                       session, seed (hududlar ro'yxati), lite (SQLite tayyorlash)
    │   ├── core/                     aqi.py (hisoblash), geo.py, memory_cache.py, i18n + locales/uz,ru, messages.py
    │   ├── services/                 air_quality.py (fetch_air_quality), alerts, messaging, complaints, ...
    │   ├── bot/                      factory, keyboards, states (FSM), middlewares, handlers/
    │   ├── api/main.py               FastAPI (health, webhook, polling lifespan)
    │   └── tasks/                    Celery: air_quality (30 daqiqa), notifications (alert, digest); lite.py (Celery'siz jadval)
    └── tests/                        127 ta test
```

## Yo'l tanlash: Docker yoki yengil rejim

| | Docker (to'liq) | Yengil rejim |
|---|---|---|
| Kerak | Docker | faqat Python 3.11+ (taxminan 110 MB) |
| Baza | PostgreSQL | SQLite fayl (`havo.db`) |
| Kesh va FSM | Redis | xotirada (qayta ishga tushsa tozalanadi) |
| Fon vazifalari | Celery worker + beat | API jarayonining ichida |
| Qachon | server, doimiy ishlash, keyingi rivojlantirish | bitta kompyuterda sinash, taqdimot |

Funksiyalar bir xil: bot, AQI, murojaatlar, ogohlantirishlar, ertalabki xabar. Yengil rejimda
migratsiya yo'q (jadvallar o'zi yaratiladi), shuning uchun keyingi versiyada baza tuzilishi o'zgarsa
`havo.db` ni o'chirib qayta yaratasiz. Doimiy ishlatish uchun Docker yo'lidan foydalaning.

## Yengil rejimda ishga tushirish (Docker'siz)

Windows (PowerShell yoki CMD):

```
cd havo-monitoring\backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lite.txt
copy .env.lite.example .env
notepad .env
.venv\Scripts\python -m uvicorn app.api.main:app
```

Mac / Linux:

```bash
cd havo-monitoring/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lite.txt
cp .env.lite.example .env && nano .env
.venv/bin/python -m uvicorn app.api.main:app
```

`.env` ichida faqat `BOT_TOKEN` va `OWM_API_KEY` ni to'ldiring. Jurnalda "Yengil rejim ..." va
"Bot polling rejimida ishga tushdi" qatorlari chiqsa, bot ishlayapti: Telegram'da `/start` yozing.
To'xtatish: `Ctrl+C`. Havo ma'lumoti ishga tushgandan 5 soniya keyin birinchi marta olinadi, so'ng
har 30 daqiqada yangilanadi; bot ishlab turgan vaqtda (kompyuter yoqiq bo'lsa) ertalabki xabar ham ketadi.
Kompyuter o'chiq yoki uyquda bo'lsa bot javob bermaydi va ogohlantirishlar ketmaydi.

Murojaatlarni ko'rish (SQLite): `havo.db` ni <https://sqlitebrowser.org> yoki VS Code'dagi SQLite
kengaytmasi bilan oching, `complaints` jadvaliga qarang.

## Tez ishga tushirish (Docker)

```bash
cp .env.example .env        # BOT_TOKEN (@BotFather), OWM_API_KEY, POSTGRES_PASSWORD ni to'ldiring
docker compose up -d --build
docker compose logs -f api worker
```

Bot `BOT_MODE=polling` rejimida darhol ishlaydi (domen va HTTPS shart emas). Telegram'da botga `/start` yozing.
API: <http://localhost:8000/docs>, holat: <http://localhost:8000/health/ready>.

**Serverda (webhook):** `.env` da `BOT_MODE=webhook`, `WEBHOOK_BASE_URL=https://domeningiz.uz`,
`WEBHOOK_SECRET=<tasodifiy qator>` ni bering, HTTPS sertifikat oling va
`docker compose --profile prod up -d` ni ishga tushiring (`nginx/default.conf` ichida TLS bo'yicha izoh bor).

## Lokal ishlab chiqish (Docker'siz)

PostgreSQL va Redis kerak. `.env` ichida `DATABASE_URL` va `REDIS_URL` ni moslang.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head && python -m app.db.seed
uvicorn app.api.main:app --reload                                   # API (+ bot, polling)
celery -A app.tasks.celery_app.celery_app worker -l info            # alohida terminalda
celery -A app.tasks.celery_app.celery_app beat -l info              # alohida terminalda
pytest                                                              # SQLite'da, tashqi xizmatlarsiz
TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/test_services_db.py tests/test_bot_flows.py
```

## Asosiy sozlamalar (.env)

| Nom | Standart | Izoh |
|---|---|---|
| `BOT_TOKEN` | | @BotFather tokeni. Bo'sh bo'lsa faqat API ishlaydi |
| `BOT_MODE` | `polling` | `polling` yoki `webhook` |
| `LITE_MODE` | `false` | `true` bo'lsa SQLite + xotirada kesh + ichki jadval (Docker'siz) |
| `OWM_API_KEY` | | OpenWeatherMap kaliti |
| `FETCH_INTERVAL_MINUTES` | `30` | Toshkent tumanlarini yangilash oralig'i (beat'ni qayta ishga tushiring) |
| `READING_TTL_MINUTES` | `30` | Viloyatlar va kesh uchun ma'lumot "yangi" hisoblanadigan vaqt |
| `ALERT_THRESHOLD` | `150` | Shundan yuqori AQI da ogohlantirish |
| `ALERT_CLEAR_THRESHOLD` | `130` | AQI shundan pastga tushganda holat tozalanadi |
| `ALERT_REPEAT_HOURS` | `6` | Havo yomon bo'lib tursa, qayta xabar oralig'i |
| `DAILY_DIGEST_HOUR` | `7` | Ertalabki xabar vaqti (`TIMEZONE` bo'yicha) |
| `MAX_COMPLAINTS_PER_DAY` | `5` | Bir foydalanuvchi uchun kunlik murojaat limiti |
| `MAX_DISTRICT_DISTANCE_KM` | `100` | GPS shu masofadan uzoq bo'lsa hudud aniqlanmaydi |

## Muhim qarorlar

- **Provayder almashtiriladi.** `AirQualityProvider` interfeysi bor; WAQI qo'shish uchun yangi klass yozib, `build_provider` ni o'zgartirish yetarli.
- **AQI o'zimizda hisoblanadi** (US EPA jadvali, PM2.5 uchun 2024 yangilanishi). OWM ning 1-5 shkalasi ishlatilmaydi.
- **GPS saqlanmaydi.** Foydalanuvchining joylashuvi faqat eng yaqin hududni aniqlash uchun ishlatiladi. Murojaatdagi koordinata esa murojaat bilan birga saqlanadi.
- **Ogohlantirish gisterezisi.** AQI 150 dan oshganda bir marta xabar; 130 gacha tushmaguncha yoki 6 soat o'tmaguncha qaytarilmaydi.
- **Bot bloklangan foydalanuvchilar** avtomatik nofaol qilinadi; qaytib yozsa yana faollashadi.
- **Telegram limiti:** ommaviy xabarlar sekundiga ~25 ta tezlikda yuboriladi, `RetryAfter` hisobga olinadi.

## Cheklovlar va keyingi qadamlar

**Bilish kerak:**
- Tuman koordinatalari **taxminiy markaz** qiymatlari (`app/db/seed_data.py`). Hudud eng yaqin markazga qarab aniqlanadi, tuman chegarasiga qarab emas. Ishlab chiqarishdan oldin OpenStreetMap yoki rasmiy GeoJSON bilan tekshiring; aniq chegara kerak bo'lsa PostGIS'ga o'ting.
- OpenWeatherMap **modellashtirilgan** ma'lumot beradi, bu o'lchov stansiyasi emas. AQI esa soatlik qiymatdan hisoblanadi (rasmiy AQI 24 soatlik o'rtachaga tayanadi), shuning uchun taxminiy baho.
- OWM tarif limitini tekshiring: Toshkent uchun kuniga 12 × 48 = 576 so'rov ketadi, viloyatlar so'rov bo'yicha qo'shiladi.
- Polling rejimida API'ni **bitta nusxada** ishga tushiring (Telegram bitta polling'ga ruxsat beradi). Beat ham bitta nusxa bo'lsin.
- Ogohlantirish holati saqlangach xabar navbatga qo'yiladi; shu orada broker ishlamasa, o'sha xabar yo'qolishi mumkin.
- Murojaat rasmlari `media` volume'ida saqlanadi: zaxira nusxa oling.

**Keyingi bosqich:**
1. Admin API: JWT login, statistika, murojaatlar ro'yxati/filtri/holat o'zgartirish, CSV/Excel eksport, broadcast (`services/messaging.send_many` tayyor).
2. React dashboard: statistika kartalari, tumanlar xaritasi va heatmap, murojaatlar CRM'i.
3. Murojaat holati o'zgarganda foydalanuvchiga xabar yuborish.
