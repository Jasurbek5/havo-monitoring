"""O'zbekcha matnlar. Matnlar HTML parse_mode da yuboriladi. Figurali qavs faqat {nom} uchun."""

TEXTS: dict[str, str] = {
    # --- Umumiy ---
    "choose_language": "Tilni tanlang / Выберите язык / Choose language",
    "lang_set": "✅ Til o'zgartirildi: O'zbekcha",
    "welcome": (
        "Assalomu alaykum! 👋\n"
        "Bu bot Toshkent havosining holatini ko'rsatadi, sog'liq bo'yicha tavsiyalar beradi "
        "va havo ifloslanishi haqida murojaat qoldirish imkonini beradi."
    ),
    "welcome_back": "Yana salom! Quyidagi menyudan tanlang.",
    "menu_hint": "Iltimos, quyidagi menyudan foydalaning.",
    "cancelled": "Bekor qilindi.",
    # --- Tugmalar ---
    "btn_air": "🌫 Havo sifati",
    "btn_complaint": "📝 Murojaat yuborish",
    "btn_alerts": "🔔 Ogohlantirishlar",
    "btn_district": "📍 Hududim",
    "btn_language": "🌐 Til",
    "btn_refresh": "🔄 Yangilash",
    "btn_other_district": "📍 Boshqa tuman",
    "btn_cancel": "❌ Bekor qilish",
    "btn_skip": "⏭ O'tkazib yuborish",
    "btn_confirm": "✅ Yuborish",
    "btn_send_location": "📍 Joylashuvimni yuborish",
    "btn_choose_list": "🏙 Ro'yxatdan tanlash",
    "btn_use_my_district": "📍 Hududim markazidan foydalanish",
    "btn_other_region": "Boshqa hudud ➡️",
    "btn_back_city": "⬅️ Toshkent shahri",
    # --- Hudud tanlash ---
    "ask_district": (
        "📍 Hududingizni aniqlash uchun joylashuvingizni yuboring yoki ro'yxatdan tanlang.\n\n"
        "Joylashuv faqat eng yaqin hududni aniqlash uchun ishlatiladi va saqlanmaydi."
    ),
    "choose_district": "Hududni tanlang:",
    "district_set": "✅ Hudud saqlandi: <b>{name}</b>",
    "district_detected": "✅ Hudud aniqlandi: <b>{name}</b>",
    "district_not_found": "Joylashuvingiz bo'yicha hudud topilmadi. Iltimos, ro'yxatdan tanlang.",
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
    "air_stale": "\n\n⚠️ <i>Yangi ma'lumot olinmadi, oxirgi ma'lum o'lchov ko'rsatilmoqda.</i>",
    "air_unavailable": "Hozircha havo ma'lumotini olib bo'lmadi. Birozdan so'ng qayta urinib ko'ring.",
    "air_not_updated": "Ma'lumot hali yangilanmagan",
    "pick_district_view": "Qaysi hudud havosini ko'rmoqchisiz?",
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
    "settings_title": "🔔 <b>Ogohlantirishlar</b>\nXavfli havo va ertalabki xabar sozlamalari:",
    "toggle_alert": "🚨 Xavfli havo xabari: {state}",
    "toggle_digest": "☀️ Ertalabki xabar: {state}",
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
