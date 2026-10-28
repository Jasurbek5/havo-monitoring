"""O'zbekcha matnlar. Matnlar HTML parse_mode da yuboriladi. Figurali qavs faqat {nom} uchun."""

TEXTS: dict[str, str] = {
    # --- Umumiy ---
    "choose_language": "Tilni tanlang / Выберите язык / Choose language",
    "lang_set": "✅ Til o'zgartirildi: O'zbekcha",
    "welcome": (
        "Assalomu alaykum! 👋\n"
        "Bu bot havo sifati va ob-havo holatini ko'rsatadi, sog'liq bo'yicha tavsiyalar beradi "
        "va havo ifloslanishi haqida murojaat qoldirish imkonini beradi."
    ),
    "welcome_back": "Yana salom! Quyidagi menyudan tanlang.",
    "menu_hint": "Iltimos, quyidagi menyudan foydalaning.",
    "cancelled": "Bekor qilindi.",
    # --- Tugmalar ---
    "btn_air": "🌫 Havo & Ob-havo",
    "btn_weather": "🌤 To'liq ob-havo",
    "btn_today_weather": "🌤 Bugungi to'liq ob-havo",
    "btn_weekly_weather": "📅 Haftalik ob-havo (7 kun)",
    "btn_back_to_air": "⬅️ Umumiy holat",
    "btn_back_to_today": "⬅️ Bugungi ob-havo",
    "btn_complaint": "📝 Murojaat yuborish",
    "btn_alerts": "🔔 Ogohlantirishlar",
    "btn_district": "📍 Hududim",
    "btn_language": "🌐 Til",
    "btn_refresh": "🔄 Yangilash",
    "btn_other_district": "📍 Boshqa hudud",
    "btn_cancel": "❌ Bekor qilish",
    "btn_skip": "⏭ O'tkazib yuborish",
    "btn_confirm": "✅ Yuborish",
    "btn_send_location": "📍 Joylashuvimni yuborish",
    "btn_search_city": "🔍 Qidirish (shahar/tuman)",
    "btn_choose_list": "🏙 Ro'yxatdan tanlash",
    "btn_use_my_district": "📍 Hududim markazidan foydalanish",
    "btn_other_region": "Boshqa hududlar ➡️",
    "btn_back_city": "⬅️ Toshkent shahri",
    # --- Hudud tanlash ---
    "ask_district": (
        "📍 Hududingizni aniqlash uchun joylashuvingizni yuboring, shahar nomini qidiring yoki ro'yxatdan tanlang.\n\n"
        "Joylashuv butun dunyo bo'ylab avtomatik aniqlanadi."
    ),
    "choose_district": "Hududni tanlang:",
    "ask_search_city": (
        "🔍 Qidirmoqchi bo'lgan shahar yoki tuman nomini kiriting:\n"
        "<i>(Masalan: Samarqand, Urgut, Qo'qon, Xiva, Istanbul, Moskva...)</i>"
    ),
    "search_results": "Quyidagi natijalar topildi. O'z hududingizni tanlang:",
    "search_not_found": "Kechirasiz, bunday nomli shahar yoki tuman topilmadi. Qayta urinib ko'ring yoki joylashuvingizni yuboring.",
    "district_set": "✅ Hudud saqlandi: <b>{name}</b>",
    "district_set_first": (
        "✅ Hudud saqlandi: <b>{name}</b>\n\n"
        "🏠 Bu hudud avtomatik ravishda sizning <b>Uy hududingiz</b> qilib belgilandi. "
        "Ertalabki ob-havo va xavfli havo ogohlantirishlari shu hudud bo'yicha yuboriladi. "
        "Boshqa joyga borganingizda ham uyingiz havosidan xabardor bo'lib turasiz!"
    ),
    "district_changed_notice": (
        "📍 Joriy hududingiz: <b>{current}</b>\n\n"
        "🏠 <b>Eslatma:</b> Sizning asosiy uy hududingiz — <b>{home}</b>.\n"
        "Ertalabki xabarnoma va xavfli havo ogohlantirishlari aynan <b>{home}</b> bo'yicha kelaveradi. "
        "Xohlasangiz «Ogohlantirishlar» menyusidan uy hududini o'zgartirishingiz mumkin."
    ),
    "district_detected": "✅ Hudud aniqlandi: <b>{name}</b>",
    "district_not_found": "Joylashuvingiz bo'yicha hudud topilmadi. Iltimos, qidiruvdan foydalaning yoki ro'yxatdan tanlang.",
    "my_district": (
        "📍 Hududingiz: <b>{name}</b>\n"
        "O'zgartirish uchun joylashuvingizni yuboring yoki ro'yxatdan tanlang."
    ),
    "need_district": "Avval hududingizni tanlang.",
    # --- Havo sifati ---
    "level_good": "Yaxshi",
    "level_moderate": "O'rtacha",
    "level_unhealthy": "Zararli",
    "level_dangerous": "Xavfli",
    "advice_good": "• Havo toza. Ochiq havoda sayr qilishingiz mumkin.",
    "advice_moderate": (
        "• Havo sifati qoniqarli.\n"
        "• Juda sezgir odamlar uzoq vaqt ochiq havoda bo'lmagani ma'qul."
    ),
    "advice_unhealthy": (
        "• Bolalar, keksalar va nafas yo'li kasalligi borlar ko'chada kamroq bo'lsin.\n"
        "• Derazalarni ochmang.\n"
        "• Tashqarida niqob (FFP2/N95) taqing."
    ),
    "advice_dangerous": (
        "• Imkon bo'lsa uyda qoling.\n"
        "• Derazalarni yoping, havo tozalagich ishlating.\n"
        "• Tashqariga chiqsangiz FFP2/N95 niqob taqing.\n"
        "• Ochiq havoda jismoniy mashq qilmang."
    ),
    "air_message": (
        "📍 <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Holat: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "🔬 <b>Ifloslantiruvchi moddalar:</b>\n"
        "  ▫️ PM2.5: {pm25} µg/m³ <i>(mayda chang)</i>\n"
        "  ▫️ PM10: {pm10} µg/m³ <i>(yirik chang)</i>\n\n"
        "💡 <b>Tavsiyalar:</b>\n"
        "{advice}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐 <i>Yangilangan: {time}</i>"
    ),
    "air_weather_message": (
        "📍 <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} <b>Ob-havo:</b> {weather_desc}, <b>{temp}°C</b>\n"
        "🌡 Sezilishi: <b>{feels_like}°C</b>\n"
        "💧 Namlik: <b>{humidity}%</b> · 💨 Shamol: <b>{wind} m/s</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Havo sifati: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n"
        "  ▫️ PM2.5: {pm25} µg/m³ · PM10: {pm10} µg/m³\n\n"
        "💡 <b>Tavsiya:</b>\n"
        "{advice}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐 <i>Yangilangan: {time}</i>"
    ),
    "full_weather_message": (
        "🌤 <b>Bugungi to'liq ob-havo: {district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} Holat: <b>{weather_desc}</b>\n\n"
        "🌡 <b>Harorat ko'rsatkichlari:</b>\n"
        "  • Hozir: <b>{temp}°C</b> <i>(sezilishi: {feels_like}°C)</i>\n"
        "  • Bugun: Min <b>{temp_min}°C</b> / Maks <b>{temp_max}°C</b>\n\n"
        "💧 Namlik: <b>{humidity}%</b>\n"
        "💨 Shamol: <b>{wind_speed} m/s</b> <i>({wind_dir})</i>\n"
        "⏱ Bosim: <b>{pressure_mmhg} mm sim. ust.</b> <i>({pressure_hpa} hPa)</i>\n"
        "{sun_times}\n"
        "💡 <b>Tavsiya:</b>\n"
        "{weather_tip}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐 <i>Yangilangan: {time}</i>"
    ),
    "sun_times_format": "🌅 Quyosh chiqishi: <b>{sunrise}</b> | Botishi: <b>{sunset}</b>\n",
    "weekly_weather_header": (
        "📅 <b>7 kunlik ob-havo prognozi: {district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    ),
    "weekly_weather_item": "🔹 <b>{day_name}</b> ({date}):\n  {emoji} {condition}, <b>{temp_max}° / {temp_min}°</b> · 💨 {wind} m/s{precip}\n\n",
    "weekly_weather_precip": " · 🌧 {prob}%",
    "weather_unavailable": "Hozircha ob-havo ma'lumotini olib bo'lmadi. Birozdan so'ng qayta urinib ko'ring.",
    "air_stale": "\n\n⚠️ <i>Yangi ma'lumot olinmadi, oxirgi ma'lum o'lchov ko'rsatilmoqda.</i>",
    "air_unavailable": "Hozircha havo ma'lumotini olib bo'lmadi. Birozdan so'ng qayta urinib ko'ring.",
    "air_not_updated": "Ma'lumot hali yangilanmagan",
    "pick_district_view": "Qaysi hudud havosini ko'rmoqchisiz?",

    # --- Shamol yo'nalishlari ---
    "wind_n": "Shimoliy",
    "wind_ne": "Shimoli-sharqiy",
    "wind_e": "Sharqiy",
    "wind_se": "Janubi-sharqiy",
    "wind_s": "Janubiy",
    "wind_sw": "Janubi-g'arbiy",
    "wind_w": "G'arbiy",
    "wind_nw": "Shimoli-g'arbiy",

    # --- Hafta kunlari ---
    "day_today": "Bugun",
    "day_tomorrow": "Ertaga",
    "weekday_0": "Dushanba",
    "weekday_1": "Seshanba",
    "weekday_2": "Chorshanba",
    "weekday_3": "Payshanba",
    "weekday_4": "Juma",
    "weekday_5": "Shanba",
    "weekday_6": "Yakshanba",

    # --- Ob-havo holatlari ---
    "weather_clear": "Ochiq havo",
    "weather_mostly_clear": "Asosan ochiq",
    "weather_partly_cloudy": "Qisman bulutli",
    "weather_cloudy": "Bulutli",
    "weather_fog": "Tuman",
    "weather_depositing_rime_fog": "Qirovli tuman",
    "weather_light_drizzle": "Kuchsiz shivalovchi yomg'ir",
    "weather_moderate_drizzle": "Shivalovchi yomg'ir",
    "weather_dense_drizzle": "Qalin shivalovchi yomg'ir",
    "weather_slight_rain": "Kuchsiz yomg'ir",
    "weather_moderate_rain": "Yomg'ir",
    "weather_heavy_rain": "Kuchli yomg'ir",
    "weather_slight_snow": "Kuchsiz qor",
    "weather_moderate_snow": "Qor",
    "weather_heavy_snow": "Kuchli qor",
    "weather_snow_grains": "Qor donachalari",
    "weather_slight_showers": "Kuchsiz jala",
    "weather_moderate_showers": "Jala",
    "weather_violent_showers": "Kuchli jala",
    "weather_snow_showers": "Qor aralash jala",
    "weather_heavy_snow_showers": "Kuchli qor aralash jala",
    "weather_thunderstorm": "Momaqaldiroq",
    "weather_thunderstorm_slight_hail": "Do'lli momaqaldiroq",
    "weather_thunderstorm_heavy_hail": "Kuchli do'lli momaqaldiroq",

    # --- Aqlli maslahatlar ---
    "weather_tip_rain": "• Tashqarida yomg'ir yog'ishi kutilmoqda. Soyabon olishni unutmang! 🌧",
    "weather_tip_snow": "• Qor yog'ishi mumkin. Qalinroq kiyining va yo'lda ehtiyot bo'ling! ❄️",
    "weather_tip_cold": "• Havo salqin. Shamollab qolmaslik uchun iliqroq kiyining! 🧥",
    "weather_tip_hot": "• Havo ancha issiq. Ko'proq suv iching va quyoshdan saqlaning! 🥤",
    "weather_tip_pleasant": "• Havo juda yoqimli va me'yorida. Sayr qilish uchun qulay vaqt! 🌿",
    # --- Ogohlantirishlar ---
    "alert_message": (
        "🔴 <b>Diqqat: {district} hududida havo xavfli darajada!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 AQI: <b>{aqi}</b> · PM2.5: {pm25} µg/m³\n\n"
        "💡 <b>Tavsiya:</b>\n"
        "{advice}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ <i>Bu xabarni «🔔 Ogohlantirishlar» bo'limida o'chirishingiz mumkin.</i>"
    ),
    "digest_message": (
        "☀️ <b>Xayrli tong!</b>\n"
        "📍 Hudud: <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Holat: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "💡 <b>Tavsiya:</b>\n"
        "{advice}"
    ),
    "digest_message_weather": (
        "☀️ <b>Xayrli tong!</b>\n"
        "📍 Hudud: <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} Bugun ob-havo: <b>{temp}°C</b> <i>({weather_desc})</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Havo sifati: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "💡 <b>Tavsiya:</b>\n"
        "{advice}"
        "{switch_hint}"
    ),
    "digest_message_weather_home": (
        "☀️ <b>Xayrli tong!</b>\n"
        "🏠 <b>Uy hududingiz: {district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} Bugun ob-havo: <b>{temp}°C</b> <i>({weather_desc})</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Havo sifati: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "💡 <b>Tavsiya:</b>\n"
        "{advice}"
        "{switch_hint}"
    ),
    "digest_switch_hint": (
        "\n\n📍 <i>Hozirgi ({other_district}) hududi ma'lumotini ko'rish uchun pastdagi tugmani bosing.</i>"
    ),
    "settings_title": "🔔 <b>Ogohlantirishlar va bildirishnomalar</b>\nXavfli havo, ertalabki xabar va uy hududi sozlamalari:",
    "toggle_alert": "🚨 Xavfli havo xabari: {state}",
    "toggle_digest": "☀️ Ertalabki xabar: {state}",
    "toggle_time": "⏰ Xabar vaqti: {time}",
    "toggle_timezone": "🕒 Vaqt mintaqasi: {tz}",
    "choose_timezone": "🕒 <b>Vaqt mintaqasini tanlang:</b>\n\n«🌐 Avtomatik» rejimida har bir shahar/hududning (masalan, Toshkent, Tokio, London) o'z mahalliy vaqti ko'rsatiladi.",
    "timezone_set": "✅ Vaqt mintaqasi: <b>{tz}</b>",
    "tz_auto": "🌐 Avtomatik (hudud vaqti)",
    "tz_tashkent": "🇺🇿 Toshkent (UTC+5)",
    "tz_moscow": "🇷🇺 Moskva (UTC+3)",
    "tz_tokyo": "🇯🇵 Tokio (UTC+9)",
    "tz_dubai": "🇦🇪 Dubay (UTC+4)",
    "tz_almaty": "🇰🇿 Olmaota (UTC+5)",
    "tz_istanbul": "🇹🇷 Istanbul (UTC+3)",
    "tz_london": "🇬🇧 London (UTC+0)",
    "tz_new_york": "🇺🇸 Nyu-York (UTC-5)",
    "tz_utc": "⏱ UTC (+0)",
    "toggle_home": "🏠 Uy hududi: {name}",
    "choose_digest_time": "⏰ Ertalabki xabar yuboriladigan vaqtni tanlang:",
    "digest_time_set": "✅ Ertalabki xabar vaqti: <b>{time}</b>",
    "home_title": (
        "🏠 <b>Uy hududi sozlamasi</b>\n\n"
        "Boshqa shahar yoki hududga borganda ham ertalabki xabarnoma va xavfli havo ogohlantirishlari "
        "aynan shu uy hududingiz bo'yicha yuboriladi.\n\n"
        "Hozirgi uy hududingiz: <b>{name}</b>"
    ),
    "btn_set_current_as_home": "🏠 Hozirgi hududni ({name}) uy qilish",
    "btn_choose_from_list": "🏙 Ro'yxatdan tanlash",
    "btn_clear_home": "❌ Uy hududini o'chirish",
    "btn_back": "⬅️ Orqaga",
    "home_district_set": "✅ Uy hududi saqlandi: <b>{name}</b>",
    "home_district_cleared": "Uy hududi sozlamasi o'chirildi.",
    "btn_switch_to_home": "🏠 {name} (Uy)",
    "btn_switch_to_other": "📍 {name}",
    "btn_all_districts": "🏙 Boshqa hududlar",
    "my_district_info": (
        "📍 Joriy hududingiz: <b>{current}</b>\n"
        "🏠 Uy hududingiz: <b>{home}</b>\n\n"
        "O'zgartirish uchun joylashuvingizni yuboring yoki quyidagilardan tanlang:"
    ),
    "btn_set_home_prompt": "🏠 Shu hududni uy qilib saqlash",
    "state_on": "yoqilgan ✅",
    "state_off": "o'chirilgan ❌",
    # --- Murojaat ---
    "cmp_limit": (
        "Bir kunda eng ko'pi bilan {limit} ta murojaat yuborish mumkin. "
        "Iltimos, ertaga qayta urinib ko'ring."
    ),
    "cmp_choose_category": "📝 <b>Murojaat</b>\n1/4 — Murojaat turini tanlang:",
    "cat_burning": "🔥 Chiqindi / o't yoqish",
    "cat_industrial": "🏭 Sanoat chiqindisi",
    "cat_smoke_dust": "💨 Tutun / chang",
    "cat_transport": "🚗 Transport",
    "cat_tree_cutting": "🌳 Daraxtlarni noqonuniy kesish",
    "cat_other": "❓ Boshqa",
    "cmp_send_photo": "2/4 — Voqea rasmini yuboring (ixtiyoriy).",
    "cmp_photo_expected": "Iltimos, rasm yuboring yoki «O'tkazib yuborish» tugmasini bosing.",
    "cmp_send_location": (
        "3/4 — Voqea joylashuvini yuboring («📍 Joylashuvimni yuborish» tugmasi orqali). "
        "Aniq joy noma'lum bo'lsa, hududingiz markazidan foydalanishingiz mumkin."
    ),
    "cmp_location_expected": "Iltimos, pastdagi tugma orqali joylashuv yuboring.",
    "cmp_write_text": "4/4 — Qisqacha tavsif yozing (kamida 5 ta, ko'pi bilan 1000 ta belgi).",
    "cmp_text_invalid": "Tavsif 5 dan 1000 gacha belgidan iborat bo'lishi kerak. Qayta yozing.",
    "cmp_confirm": (
        "📋 <b>Murojaatni tekshiring</b>\n\n"
        "Turi: {category}\n"
        "Hudud: {district}\n"
        "Joylashuv: {location}\n"
        "Rasm: {photo}\n\n"
        "Tavsif: {text}"
    ),
    "loc_exact": "aniq nuqta",
    "loc_approx": "hudud markazi (taxminiy)",
    "photo_yes": "bor",
    "photo_no": "yo'q",
    "cmp_saved": "✅ Murojaatingiz <b>№{id}</b> qabul qilindi. Rahmat!",
    "cmp_error": "Murojaatni saqlashda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
    "cmp_session_expired": "Murojaat ma'lumotlari topilmadi. Iltimos, qaytadan boshlang.",
}
