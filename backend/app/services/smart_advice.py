"""Ko'p faktorli aqlli tavsiyalar tizimi (Smart Advice Engine).

Havo sifati (AQI, PM2.5), harorat, tuyulishi, yog'ingarchilik (yomg'ir, qor),
UV indeksi, namlik va shamol tezligini birgalikda tahlil qilib, foydalanuvchiga
kundalik amaliy tavsiyalar (kiyim, tashqarida/aksessuar, salomatlik) beradi.
"""

from __future__ import annotations

from typing import Any


def generate_smart_advice(
    *,
    aqi: int | None,
    temp: float,
    feels_like: float,
    weather_code: int = 0,
    humidity: int = 45,
    wind_speed: float = 2.0,
    uv_index: int = 3,
    lang: str = "uz",
) -> dict[str, Any]:
    """AQI va ob-havo parametrlarini tahlil qilib 3 ta amaliy tavsiya qaytaradi."""

    t_eff = feels_like if feels_like is not None else temp

    # ----------------------------------------------------
    # 1. KIYIM (Clothing) — Harorat va tuyulishiga qarab
    # ----------------------------------------------------
    clothing_icon = "🧥"
    if t_eff < 0:
        clothing_icon = "🧤"
        clothing_uz = "Qishki qalin palto, bosh kiyim va qo'lqop kiying (sovuq)"
        clothing_ru = "Наденьте теплую зимнюю одежду, шапку и перчатки"
        clothing_en = "Heavy winter coat, warm hat and gloves recommended"
    elif t_eff < 10:
        clothing_icon = "🧥"
        clothing_uz = "Qalin kurtka yoki issiq palto kiyish tavsiya etiladi"
        clothing_ru = "Рекомендуется теплая куртка или пальто"
        clothing_en = "Warm jacket or coat is recommended"
    elif t_eff < 18:
        clothing_icon = "🧥"
        clothing_uz = "Havo salqin, yengil kurtka yoki sviter kiyish ma'qul"
        clothing_ru = "Прохладно, наденьте легкую куртку или свитер"
        clothing_en = "Cool weather, light jacket or sweater is suitable"
    elif t_eff < 26:
        clothing_icon = "👕"
        clothing_uz = "Havo qulay va iliq, yengil kiyim mos keladi"
        clothing_ru = "Комфортная погода, подойдет легкая одежда"
        clothing_en = "Pleasant and mild, comfortable everyday clothes"
    elif t_eff < 34:
        clothing_icon = "👕"
        clothing_uz = "Havo issiq, paxtali va yengil yozgi kiyim kiying"
        clothing_ru = "Тепло, выбирайте легкую дышащую одежду"
        clothing_en = "Warm weather, wear light and breathable clothes"
    else:
        clothing_icon = "🧢"
        clothing_uz = "Jazirama issiq! Yengil ochiq kiyim va bosh kiyim kiying"
        clothing_ru = "Сильная жара! Наденьте светлую одежду и головной убор"
        clothing_en = "Very hot! Wear light clothing and a sun hat"

    if lang == "ru":
        clothing_text = clothing_ru
        clothing_badge = "Одежда"
    elif lang == "en":
        clothing_text = clothing_en
        clothing_badge = "Clothing"
    else:
        clothing_text = clothing_uz
        clothing_badge = "Kiyim"

    # ----------------------------------------------------
    # 2. TASHQARIDA / AKSESSUAR (Outdoors & Weather factors)
    # ----------------------------------------------------
    # WMO kodlar bo'yicha:
    # Momaqaldiroq: 95, 96, 99
    # Yomg'ir: 51-67, 80-82
    # Qor: 71-77, 85, 86
    is_thunder = weather_code in (95, 96, 99)
    is_rain = weather_code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82)
    is_snow = weather_code in (71, 73, 75, 77, 85, 86)

    outdoors_icon = "🌤"
    if is_thunder:
        outdoors_icon = "⚡"
        outdoors_uz = "Momaqaldiroq kutilmoqda, ochiq maydonda turmang"
        outdoors_ru = "Ожидается гроза, избегайте открытых пространств"
        outdoors_en = "Thunderstorm expected, seek safe shelter indoors"
    elif is_rain:
        outdoors_icon = "☂️"
        outdoors_uz = "Yomg'ir yog'moqda, soyabon olishni unutmang"
        outdoors_ru = "Идет дождь, обязательно возьмите зонт"
        outdoors_en = "Rain is expected, carry an umbrella"
    elif is_snow:
        outdoors_icon = "❄️"
        outdoors_uz = "Qor yog'moqda, sirpanchiq yo'llardan ehtiyot bo'ling"
        outdoors_ru = "Идет снег, будьте осторожны на скользких дорогах"
        outdoors_en = "Snow is falling, watch your step on slippery paths"
    elif wind_speed >= 8.0:
        outdoors_icon = "💨"
        outdoors_uz = f"Kuchli shamol ({round(wind_speed, 1)} m/s), ehtiyot bo'ling"
        outdoors_ru = f"Сильный ветер ({round(wind_speed, 1)} м/с), будьте внимательны"
        outdoors_en = f"Brisk wind ({round(wind_speed, 1)} m/s), be cautious outdoors"
    elif uv_index >= 6:
        outdoors_icon = "🕶"
        outdoors_uz = f"Quyosh faol (UV {uv_index}), ko'zoynak va bosh kiyim oling"
        outdoors_ru = f"Активное солнце (УФ {uv_index}), наденьте очки и кепку"
        outdoors_en = f"High UV index ({uv_index}), wear sunglasses and hat"
    elif humidity <= 25 and temp >= 24:
        outdoors_icon = "💧"
        outdoors_uz = "Havo quruq, yetarli miqdorda suv ichib turing"
        outdoors_ru = "Сухой воздух, не забывайте пить больше воды"
        outdoors_en = "Dry air conditions, remember to stay hydrated"
    else:
        outdoors_icon = "🌤"
        outdoors_uz = "Ob-havo sharoiti barqaror va tinch"
        outdoors_ru = "Погода спокойная и стабильная"
        outdoors_en = "Weather is calm and stable"

    if lang == "ru":
        outdoors_text = outdoors_ru
        outdoors_badge = "На улице"
    elif lang == "en":
        outdoors_text = outdoors_en
        outdoors_badge = "Outdoors"
    else:
        outdoors_text = outdoors_uz
        outdoors_badge = "Tashqarida"

    # ----------------------------------------------------
    # 3. SALOMATLIK VA HAVO (Air Quality & Health)
    # ----------------------------------------------------
    health_icon = "🌿"
    aqi_num = aqi if aqi is not None else 50
    if aqi_num > 200:
        health_icon = "⚠️"
        health_uz = "Xavfli havo! Derazalarni yoping, tashqarida FFP2 niqob taqing"
        health_ru = "Опасный воздух! Закройте окна, носите маску FFP2"
        health_en = "Hazardous air! Close windows, wear an FFP2 mask outdoors"
    elif aqi_num > 100:
        health_icon = "😷"
        health_uz = "Havo changli. Sezgir insonlar niqob taqishi tavsiya etiladi"
        health_ru = "Воздух загрязнен. Чувствительным людям стоит надеть маску"
        health_en = "Unhealthy air. Sensitive individuals should wear masks"
    elif aqi_num > 50:
        health_icon = "🟡"
        health_uz = "Havo qoniqarli, sezgir insonlar uzoq vaqt zo'riqmasin"
        health_ru = "Умеренное качество, чувствительным людям не перенапрягаться"
        health_en = "Moderate air quality, acceptable for most activities"
    else:
        health_icon = "🌿"
        health_uz = "Havo toza va musaffo! Sayr va xonani shamollatish uchun a'lo"
        health_ru = "Чистый и свежий воздух! Отлично для прогулок и проветривания"
        health_en = "Air is clean and fresh! Great for walks and airing rooms"

    if lang == "ru":
        health_text = health_ru
        health_badge = "Воздух"
    elif lang == "en":
        health_text = health_en
        health_badge = "Air & Health"
    else:
        health_text = health_uz
        health_badge = "Havo"

    items = [
        {
            "category": "clothing",
            "icon": clothing_icon,
            "badge": clothing_badge,
            "text": clothing_text,
        },
        {
            "category": "outdoors",
            "icon": outdoors_icon,
            "badge": outdoors_badge,
            "text": outdoors_text,
        },
        {
            "category": "health",
            "icon": health_icon,
            "badge": health_badge,
            "text": health_text,
        },
    ]

    full_text = f"{clothing_icon} {clothing_text}\n{outdoors_icon} {outdoors_text}\n{health_icon} {health_text}"

    return {
        "items": items,
        "full_text": full_text,
    }
