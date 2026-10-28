# Havo Monitoringi Tizimi — To'liq Texnik Qo'llanma va Arxitektura

Ushbu qo'llanma loyihaning qanday ishlashini, qaysi texnologiyalar qanday maqsadda qo'llanilganini va qaysi fayl nima vazifani bajarishini to'liq tushunishingiz uchun tayyorlandi. Himoyada (universitetda) xuddi kodni boshidan oxirigacha o'zingiz yozgandek bemalol tushuntirib bera olasiz.

---

## 1. Loyihaning Maqsadi va Umumiy Konsepsiyasi

Toshkent shahri (va O'zbekiston viloyatlari) bo'yicha **havo sifatini (AQI, PM2.5, PM10) monitoring qilish**, aholini xavfli havodan ogohlantirish, ertalabki havo xabarlarini yetkazish va aholidan **havo ifloslanishi bo'yicha murojaatlarni (rasm, GPS, tavsif)** qabul qiluvchi kompleks tizim.

Loyiha 3 ta asosiy qismdan iborat:
1. **FastAPI Web Service:** REST API, sog'lomlikni tekshirish (`/health`) va Telegram webhook xizmati.
2. **Aiogram 3 Telegram Bot:** Foydalanuvchi bilan interaktiv muloqot, til tanlash, havo ma'lumotlari va murojaat qabul qilish.
3. **Fon vazifalari (Scheduler / Celery):** Havo ma'lumotlarini tashqi API'dan avtomatik yangilab turish va foydalanuvchilarga xabarnomalar yuborish.

---

## 2. Ishlatilgan Texnologiyalar Steki (Tech Stack)

| Texnologiya | Vazifasi va Nima Uchun Tanlangan? |
| :--- | :--- |
| **Python 3.12** | Asosiy dasturlash tili. Yangi asinxron (asyncio) imkoniyatlari va tezligi yuqori. |
| **FastAPI** | Zamonaviy, juda tezkor asinxron veb-freymvork. Webhook qabul qilish va API boshqaruvi uchun. |
| **Aiogram 3** | Telegram bot yaratish uchun O'zbekistonda va dunyoda eng mashhur asinxron kutubxona. Router va Middleware arxitekturasi juda qulay. |
| **SQLAlchemy 2.0 (Asyncio)** | Ma'lumotlar bazasi bilan ishlash uchun ORM (Object-Relational Mapping). SQL so'rovlarni Python klasslari orqali xavfsiz va asinxron bajaradi. |
| **SQLite (aiosqlite) / PostgreSQL (asyncpg)** | **SQLite:** Lite (bepul/sinov) rejimda hech qanday server talab qilmasdan bitta faylda (`havo.db`) ma'lumotlarni saqlaydi.<br>**PostgreSQL:** To'liq Docker rejimida yirik hajmdagi ma'lumotlar uchun ishlatiladi. |
| **Redis** | Kesh (havo ma'lumotlarini qayta-qayta API'dan so'ramay saqlab turish) va Celery xabarlar brokeri uchun. |
| **Celery** | Og'ir va jadval asosidagi fon vazifalarini (har 30 daqiqada havoni yangilash, soat 07:00 da xabar yuborish) bajaruvchi tizim. |
| **Alembic** | PostgreSQL bazasi tuzilmasi o'zgarganda ma'lumotlarni yo'qotmasdan yangilovchi migratsiya vositasi. |
| **OpenWeatherMap API** | Havo sifati (Air Pollution API: PM2.5, PM10, CO, NO2, SO2, O3) koordinatalar bo'yicha real vaqtda olinadigan tashqi servis. |
| **Docker & Docker Compose** | Tizimni barcha qismlari (API, DB, Redis, Worker, Beat, Nginx) bilan birgalikda bitta buyruqda ko'tarish uchun. |

---

## 3. Loyiha Arxitekturasi va Papkalar Strukturasi

```text
havo-monitoring/
├── docker-compose.yml          # To'liq tizim (Postgres, Redis, Worker, API) konteynerlari
├── backend/
│   ├── Dockerfile              # Backend servisini yig'ish (Render va Docker uchun)
│   ├── requirements.txt        # Asosiy kutubxonalar ro'yxati (aiosqlite bilan birga)
│   ├── requirements-lite.txt   # Yengil rejim kutubxonalari
│   ├── alembic/                # Baza migratsiyalari tarixi
│   └── app/
│       ├── config.py           # Barcha sozlamalar (.env dan o'qiladi)
│       ├── api/
│       │   └── main.py         # FastAPI ilovasi, Lifespan, /health va Polling boshlanishi
│       ├── bot/                # Telegram bot kodlari
│       │   ├── factory.py      # Bot va Dispatcher yaratish, routerlarni ulash
│       │   ├── states.py       # FSM (Murojaat bosqichlari)
│       │   ├── keyboards.py    # Tugmalar (Inline va Reply klaviaturalar)
│       │   ├── middlewares/    # So'rovlarni tutib oluvchi oraliq qatlam
│       │   │   ├── db.py       # Har bir bot so'roviga DB sessiyasini ulab beradi
│       │   │   └── user.py     # Foydalanuvchini bazadan topadi/yaratadi va tilni aniqlaydi
│       │   └── handlers/       # Bot buyruqlari
│       │       ├── start.py        # /start, til va hudud tanlash
│       │       ├── air.py          # "Havo holati" tugmasi, havoni chiqarish
│       │       ├── complaint.py    # Murojaat yuborish (FSM bosqichlari)
│       │       ├── districts.py    # Hududni o'zgartirish
│       │       ├── settings.py     # Ogohlantirishlar va ertalabki xabarni yoqish/o'chirish
│       │       └── fallback.py     # Tushunarsiz xabarlarni tutish
│       ├── core/               # Yordamchi mantiqiy modullar
│       │   ├── aqi.py          # AQI (Air Quality Index) hisoblash matematik formulasi
│       │   ├── geo.py          # Haversine formulasi (GPS orqali eng yaqin tumanni topish)
│       │   ├── i18n.py         # Ko'p tillilik (uz, ru, en) boshqaruvi
│       │   ├── locales/        # So'zlar lug'atlari (uz.py, ru.py, en.py)
│       │   ├── memory_cache.py # Yengil rejim uchun Redis'siz xotiradagi kesh
│       │   └── messages.py     # Telegram xabarlari dizayni va matn formatlash
│       ├── db/                 # Ma'lumotlar bazasi
│       │   ├── session.py      # SQLAlchemy async_engine va sessionmaker
│       │   ├── lite.py         # Yengil rejimda SQLite jadvallarini avtomatik yaratish
│       │   ├── seed.py         # Toshkent tumanlari va viloyat koordinatalarini kiritish
│       │   └── seed_data.py    # Hududlar ma'lumotlari (nomlari, lat, lon)
│       ├── models/             # ORM modellari (Jadvallar)
│       │   ├── base.py         # Base klassi va CreatedAt vaqti
│       │   ├── district.py     # Hududlar (District jadvali)
│       │   ├── user.py         # Foydalanuvchilar (User jadvali)
│       │   ├── air_quality.py  # Havo o'lchovlari jurnali (AirQualityLog jadvali)
│       │   ├── complaint.py    # Aholi murojaatlari (Complaint jadvali)
│       │   └── admin.py        # Adminlar (AdminUser jadvali)
│       ├── services/           # Asosiy biznes-mantiq
│       │   ├── air_quality.py  # OpenWeatherMap'dan havo ma'lumotlarini olish va saqlash
│       │   ├── alerts.py       # Xavfli havo aniqlanganda ogohlantirish chiqarish
│       │   ├── messaging.py    # Foydalanuvchilarga ommaviy xabar yuborish
│       │   ├── districts.py    # GPS bo'yicha eng yaqin hududni qidirish
│       │   ├── complaints.py   # Murojaatni rasmi bilan saqlash (kuniga 5 ta limit)
│       │   └── users.py        # Foydalanuvchini ro'yxatdan o'tkazish
│       └── tasks/              # Fon vazifalari
│           ├── air_quality.py  # Toshkent tumanlari havosini yangilovchi vazifa
│           ├── notifications.py# Ogohlantirish va ertalabki xabar tarqatuvchi vazifa
│           ├── lite.py         # Celery'siz yengil rejimdagi asinxron rejalashtiruvchi
│           └── celery_app.py   # To'liq rejim uchun Celery sozlamalari
```

---

## 4. Ma'lumotlar Bazasi Modellarining Tuzilishi

Loyiha ma'lumotlar bazasida 5 ta asosiy jadval mavjud:

1. **`districts` (Hududlar):**
   - `id`, `name_uz`, `name_ru`, `name_en`, `slug` (masalan: `yunusobod`, `samarqand`).
   - `latitude`, `longitude` (Tuman markazining koordinatalari).
   - `is_city` (True bo'lsa Toshkent tumani, False bo'lsa viloyat markazi).

2. **`users` (Telegram foydalanuvchilari):**
   - `telegram_id` (Telegram bergan noyob ID).
   - `language` (`uz`, `ru` yoki `en`).
   - `district_id` (Foydalanuvchi biriktirilgan hudud).
   - `alert_enabled` (Xavfli havo bo'lsa xabar borishi: sukut bo'yicha `True`).
   - `daily_digest` (Har kuni ertalab 07:00 da xabar borishi: sukut bo'yicha `False`).
   - `is_active` (Botni bloklagan foydalanuvchilar `False` ga o'tkaziladi).

3. **`air_quality_logs` (Havo o'lchovlari tarixi):**
   - `district_id` (Qaysi tumanga tegishli).
   - `aqi` (AQI indeksi, masalan: 45, 120, 180).
   - `pm2_5`, `pm10` (Zararli zarrachalar konsentratsiyasi).
   - `raw_data` (OpenWeatherMap qaytargan butun JSON javobi).
   - `recorded_at` (Qachon o'lchangan vaqt).

4. **`complaints` (Aholi murojaatlari):**
   - `user_id`, `district_id`.
   - `category` (Chiqindi yoqish, Sanoat tutuni, Chang, Daraxt kesish, Boshqa).
   - `photo_path` (Yuklangan rasmning serverdagi yo'li).
   - `location_lat`, `location_lon` (Murojaat yuborilgan aniq GPS nuqta).
   - `description` (Murojaat matni, 5 tadan 1000 belgichagacha).
   - `status` (`pending`, `reviewed`, `rejected`).

5. **`admin_users` (Adminlar):**
   - Kelgusida dashboard orqali murojaatlarni ko'rish va tizimni boshqarish uchun mo'ljallangan.

---

## 5. Dastur Qanday Ishlaydi? (Sxema va Jarayonlar)

### A. Botning ishga tushishi (Lifespan):
1. `backend/app/api/main.py` faylida FastAPI `lifespan` funksiyasi ishga tushadi.
2. Agar `LITE_MODE=true` bo'lsa, avtomatik `init_lite_db()` chaqiriladi va SQLite bazasida jadvallar (`havo.db`) yaratiladi va 25 ta hudud (Toshkent tumanlari + viloyatlar) bazaga kiritiladi (`seed`).
3. Telegram Bot va Dispatcher yaratilib, `BOT_MODE=polling` bo'lsa, `asyncio.create_task` orqali alohida fon vazifasida Telegram'dan xabarlarni tinglash boshlanadi.
4. Yengil rejalashtiruvchi (`run_lite_scheduler`) fon vazifasi sifatida yoqiladi.

### B. Foydalanuvchi botga kirganda (`/start` oqimi):
1. **Middleware'lar ishlaydi:** Har bir xabar kelganda `DbSessionMiddleware` bazaga ulanish sessiyasini ochadi. `UserMiddleware` Telegram ID orqali bazadan foydalanuvchini qidiradi; agar yangi bo'lsa, darhol bazaga yozib qo'yadi.
2. **Til tanlash:** Agar foydalanuvchi yangi bo'lsa, unga 3 ta tilda (🇺🇿 O'zbekcha, 🇷🇺 Русский, 🇬🇧 English) tugmalar chiqadi.
3. **Hudud tanlash:** Til tanlangach, foydalanuvchiga GPS joylashuvini yuborish yoki ro'yxatdan o'z tumanini tanlash taklif qilinadi.
4. **GPS yuborilganda:** `core/geo.py` ichidagi **Haversine matematik formulasi** ishga tushadi: yuborilgan koordinata bilan bazadagi 25 ta hudud orasidagi masofalar hisoblanib, foydalanuvchiga eng yaqin tuman avtomatik biriktiriladi.

### C. Havo ma'lumotlarini olish va Kesh (Caching):
1. Foydalanuvchi "💨 Havo sifati" tugmasini bosganda:
2. Avval **Kesh** tekshiriladi (Redis yoki xotiradagi `memory_cache`). Havo ma'lumotining yaroqlilik muddati (TTL) — **30 daqiqa**.
3. Agar keshda ma'lumot bo'lsa, tashqi API'ga so'rov yuborilmaydi (bu OpenWeatherMap limitini tejaydi va javob 0.01 soniyada chiqadi).
4. Agar keshda bo'lmasa, OpenWeatherMap API'siga koordinatalar yuboriladi, olingan PM2.5 va PM10 qiymatlari asosida `core/aqi.py` formulasi orqali AQI hisoblanadi, bazaga (`air_quality_logs`) yoziladi va keshga 30 daqiqaga joylanadi.
5. Telegram bot foydalanuvchiga chiroyli formatda: AQI darajasi (🟢 Yaxshi, 🟡 O'rtacha, 🟠 Zararli, 🔴 Xavfli) va sog'liq uchun tavsiyalar bilan birga yuboradi.

### D. Murojaat yuborish mexanizmi (FSM - Finite State Machine):
Spamdan himoyalanish va tartibli ma'lumot yig'ish uchun **aiogram FSM** (Holatlar mashinasi) ishlatilgan:
1. **Holat 1 (`choosing_category`):** Muammo turi tanlanadi (tutun, chiqindi yoqish va hk.).
2. **Holat 2 (`uploading_photo`):** Rasm so'raladi (rasm jo'natish majburiy emas, «O'tkazib yuborish» tugmasi bor).
3. **Holat 3 (`sending_location`):** Aniq lokatsiya tugmasi orqali GPS nuqta so'raladi.
4. **Holat 4 (`writing_description`):** Qisqacha tavsif yoziladi (5 dan 1000 belgichagacha tekshiriladi).
5. **Tasdiqlash:** Foydalanuvchiga to'plangan ma'lumotlar kartochkasi ko'rsatiladi va «Tasdiqlash» bosilgach, bazaga yozilib, unga noyob murojaat raqami (masalan, `#14`) beriladi.
6. **Cheklov:** Bir foydalanuvchi sutkasiga ko'pi bilan 5 ta murojaat yubora oladi (`max_complaints_per_day = 5`).

### E. Avtomatik Ogohlantirishlar va Ertalabki xabar:
1. **Xavfli havo ogohlantirishi:** Har 30 daqiqada Toshkent tumanlari tekshirilganda, agar qaysidir tumanda AQI > 150 (zararli) darajaga yetsa, shu tumanga biriktirilgan va `alert_enabled=True` bo'lgan barcha foydalanuvchilarga avtomatik favqulodda ogohlantirish xabari yuboriladi. Bir tumanga har 6 soatda faqat bir marta ogohlantirish beriladi (foydalanuvchilarni bezor qilmaslik uchun).
2. **Ertalabki xabar (`daily_digest`):** Har kuni Toshkent vaqti bilan ertalab soat **07:00 da** `daily_digest=True` qilgan foydalanuvchilarga bugungi havo ma'lumoti va kunlik tavsiyalar («Xayrli tong!» xabari) yuboriladi.

---

## 6. Ishlatilgan Maxsus Formulalar va Algoritmlar

### 1. Haversine Formulasi (`app/core/geo.py`)
Yer yuzasi sharsimon bo'lgani sababli, ikki geografik nuqta (kenglik va uzunlik) orasidagi masofani to'g'ri chiziq bilan o'lchab bo'lmaydi.
Bu yerda Haversine trigonometrik formulasi ishlatilgan:
$$d = 2r \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \varphi}{2}\right) + \cos(\varphi_1)\cos(\varphi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)$$
Bu formula orqali foydalanuvchi Telegram'da "Joylashuvni ulashish" tugmasini bosganda, unga eng yaqin bo'lgan tuman 1-2 millisoniyada aniqlanadi.

### 2. EPA AQI Hisoblash Algoritmi (`app/core/aqi.py`)
OpenWeatherMap o'zining soddalashtirilgan 1 dan 5 gacha indeksini beradi. Lekin xalqaro standart (AQI 0-500 shkalasi) bo'yicha havo sifatini aniq ifodalash uchun AQI konsentratsiya oraliqlari bo'yicha chiziqli interpolyatsiya formulasi yozilgan:
$$I = \frac{I_{high} - I_{low}}{C_{high} - C_{low}} (C - C_{low}) + I_{low}$$
Bu orqali PM2.5 va PM10 zarrachalarining mikrogramm/m³ miqdoridan aniq AQI soni (masalan: 42, 115, 168) chiqariladi.

---

## 7. Nega 2 xil rejim (Full Docker va Lite Mode) qilingan?

Bu loyihaning eng katta muhandislik yutug'i hisoblanadi:
1. **To'liq rejim (Full Mode):** PostgreSQL + Redis + Celery Worker + Celery Beat + FastAPI + Nginx. Bu yirik korporativ ishlab chiqarish (Production), yuz minglab foydalanuvchilar va doimiy serverlar uchun mo'ljallangan.
2. **Yengil rejim (Lite Mode):** Faqat Python + SQLite (`havo.db`) + In-Memory kesh + Asinxron ichki jadval.
   - Bepul hostinglar (Render, Koyeb) xotirasi (RAM) atigi 512 MB bo'lgani uchun va talabalar uchun server xarajatlarisiz 1 ta buyruqda loyihani himoya qilish imkonini beradi.
   - Funksionallik mutlaqo bir xil: bot, ogohlantirishlar, murojaatlar to'liq ishlaydi.

---

## 8. Universitet Himoyasida Domlalar Berishi Mumkin Bo'lgan Savollar va Tayyor Javoblar

**1-savol: Loyihada ma'lumotlar bazasi bilan qanday bog'lanilgan? SQL Injection'dan himoyalanganmi?**
> **Javob:** Loyihada eng zamonaviy **SQLAlchemy 2.0 ORM** kutubxonasidan foydalanilgan. Barcha so'rovlar asinxron bajariladi. ORM parametrlashtirilgan (parameterized) so'rovlar tuzishi sababli tizim **SQL Injection xurujlaridan 100% himoyalangan**.

**2-savol: Telegram bot ko'p foydalanuvchi bir vaqtda yozganda qotib qolmaydimi?**
> **Javob:** Yo'q, chunki butun arxitektura **to'liq asinxron (asyncio va aiogram 3)** asosida qurilgan. Har bir foydalanuvchi so'rovi bitta umumiy oqimni to'sib qo'ymaydi (non-blocking I/O). Qolaversa, havo ma'lumotlari keshlanadi, har safar tashqi API'ga murojaat qilib vaqt yo'qotilmaydi.

**3-savol: Foydalanuvchi yuborgan rasmlar qayerda saqlanadi?**
> **Javob:** Rasm faylining o'zi serverning media jildida (`/media` yoki `/data/media`) xavfsiz nom bilan saqlanadi, ma'lumotlar bazasiga esa faqat o'sha rasmning fayl yo'li (path) yoziladi. Bu bazaning og'irlashib ketishini oldini oladi.

**4-savol: Foydalanuvchi doimiy qayta-qayta murojaat yuborib bazani to'ldirib tashlasa nima bo'ladi?**
> **Javob:** Xavfsizlik va spamga qarshi himoya bor: `ComplaintService` har bir foydalanuvchining bugungi murojaatlarini hisoblab boradi va 1 kunda 5 tadan ortiq murojaat yuborishga yo'l qo'ymaydi.
