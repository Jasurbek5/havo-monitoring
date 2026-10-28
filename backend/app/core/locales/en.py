"""English texts. Sent in HTML parse_mode. Curly braces only for {name} placeholders."""

TEXTS: dict[str, str] = {
    # --- General ---
    "choose_language": "Tilni tanlang / Выберите язык / Choose language",
    "lang_set": "✅ Language changed: English",
    "welcome": (
        "Hello! 👋\n"
        "This bot shows air quality and weather information, provides health recommendations, "
        "and allows submitting reports regarding air pollution."
    ),
    "welcome_back": "Welcome back! Please select an option from the menu below.",
    "menu_hint": "Please use the menu below.",
    "cancelled": "Cancelled.",
    # --- Buttons ---
    "btn_air": "🌫 Air & Weather",
    "btn_weather": "🌤 Full weather",
    "btn_today_weather": "🌤 Today's full weather",
    "btn_weekly_weather": "📅 Weekly forecast (7 days)",
    "btn_back_to_air": "⬅️ Overview",
    "btn_back_to_today": "⬅️ Today's weather",
    "btn_complaint": "📝 Submit complaint",
    "btn_alerts": "🔔 Alerts",
    "btn_district": "📍 My district",
    "btn_language": "🌐 Language",
    "btn_refresh": "🔄 Refresh",
    "btn_other_district": "📍 Other region",
    "btn_cancel": "❌ Cancel",
    "btn_skip": "⏭ Skip",
    "btn_confirm": "✅ Submit",
    "btn_send_location": "📍 Send location",
    "btn_search_city": "🔍 Search (city/district)",
    "btn_choose_list": "🏙 Choose from list",
    "btn_use_my_district": "📍 Use my district center",
    "btn_other_region": "Other regions ➡️",
    "btn_back_city": "⬅️ Tashkent city",
    # --- District selection ---
    "ask_district": (
        "📍 To determine your location, send your location, search for a city, or choose from the list.\n\n"
        "Location is detected automatically worldwide and is not stored."
    ),
    "choose_district": "Choose district:",
    "ask_search_city": (
        "🔍 Enter the name of a city or district to search:\n"
        "<i>(For example: Samarkand, Urgut, Kokand, Khiva, Istanbul, London...)</i>"
    ),
    "search_results": "The following results were found. Select your location:",
    "search_not_found": "Sorry, no city or district found with that name. Please try again or send your location.",
    "district_set": "✅ District saved: <b>{name}</b>",
    "district_set_first": (
        "✅ District saved: <b>{name}</b>\n\n"
        "🏠 This location has been automatically set as your <b>Home District</b>. "
        "Morning weather digests and hazardous air alerts will always be sent for this district "
        "even when you travel!"
    ),
    "district_changed_notice": (
        "📍 Current district: <b>{current}</b>\n\n"
        "🏠 <b>Note:</b> Your primary home district remains <b>{home}</b>.\n"
        "Morning digests and hazardous air alerts will continue to arrive for <b>{home}</b>. "
        "You can change your home district anytime in the «Alerts» settings."
    ),
    "district_detected": "✅ District detected: <b>{name}</b>",
    "district_not_found": "Could not determine district from your location. Please use search or choose from the list.",
    "my_district": (
        "📍 Your district: <b>{name}</b>\n"
        "Send your location or choose from the list to change it."
    ),
    "need_district": "Please choose your district first.",
    # --- Air quality ---
    "level_good": "Good",
    "level_moderate": "Moderate",
    "level_unhealthy": "Unhealthy",
    "level_dangerous": "Hazardous",
    "advice_good": "• Air quality is clean. You can enjoy outdoor activities.",
    "advice_moderate": (
        "• Air quality is acceptable.\n"
        "• Sensitive people should avoid prolonged outdoor exposure."
    ),
    "advice_unhealthy": (
        "• Children, the elderly, and people with respiratory conditions should stay indoors.\n"
        "• Keep windows closed.\n"
        "• Wear a mask (FFP2/N95) outdoors."
    ),
    "advice_dangerous": (
        "• Stay indoors if possible.\n"
        "• Keep windows closed, use an air purifier.\n"
        "• Wear an FFP2/N95 mask when outdoors.\n"
        "• Avoid outdoor physical exertion."
    ),
    "air_message": (
        "📍 <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Status: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "🔬 <b>Pollutant concentrations:</b>\n"
        "  ▫️ PM2.5: {pm25} µg/m³ <i>(fine particles)</i>\n"
        "  ▫️ PM10: {pm10} µg/m³ <i>(coarse dust)</i>\n\n"
        "💡 <b>Recommendations:</b>\n"
        "{advice}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐 <i>Updated: {time}</i>"
    ),
    "air_weather_message": (
        "📍 <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} <b>Weather:</b> {weather_desc}, <b>{temp}°C</b>\n"
        "🌡 Feels like: <b>{feels_like}°C</b>\n"
        "💧 Humidity: <b>{humidity}%</b> · 💨 Wind: <b>{wind} m/s</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Air quality: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n"
        "  ▫️ PM2.5: {pm25} µg/m³ · PM10: {pm10} µg/m³\n\n"
        "💡 <b>Recommendations:</b>\n"
        "{advice}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐 <i>Updated: {time}</i>"
    ),
    "full_weather_message": (
        "🌤 <b>Today's full weather: {district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} Condition: <b>{weather_desc}</b>\n\n"
        "🌡 <b>Temperature:</b>\n"
        "  • Now: <b>{temp}°C</b> <i>(feels like: {feels_like}°C)</i>\n"
        "  • Today: Min <b>{temp_min}°C</b> / Max <b>{temp_max}°C</b>\n\n"
        "💧 Humidity: <b>{humidity}%</b>\n"
        "💨 Wind: <b>{wind_speed} m/s</b> <i>({wind_dir})</i>\n"
        "⏱ Pressure: <b>{pressure_mmhg} mmHg</b> <i>({pressure_hpa} hPa)</i>\n"
        "{sun_times}\n"
        "💡 <b>Tips:</b>\n"
        "{weather_tip}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐 <i>Updated: {time}</i>"
    ),
    "sun_times_format": "🌅 Sunrise: <b>{sunrise}</b> | Sunset: <b>{sunset}</b>\n",
    "weekly_weather_header": (
        "📅 <b>7-day weather forecast: {district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    ),
    "weekly_weather_item": "🔹 <b>{day_name}</b> ({date}):\n  {emoji} {condition}, <b>{temp_max}° / {temp_min}°</b> · 💨 {wind} m/s{precip}\n\n",
    "weekly_weather_precip": " · 🌧 {prob}%",
    "weather_unavailable": "Weather data is currently unavailable. Please try again shortly.",
    "air_stale": "\n\n⚠️ <i>Fresh data could not be retrieved; showing the latest recorded reading.</i>",
    "air_unavailable": "Air quality data is currently unavailable. Please try again shortly.",
    "air_not_updated": "Data is not updated yet",
    "pick_district_view": "Which district's air quality would you like to view?",

    # --- Wind directions ---
    "wind_n": "North",
    "wind_ne": "North-East",
    "wind_e": "East",
    "wind_se": "South-East",
    "wind_s": "South",
    "wind_sw": "South-West",
    "wind_w": "West",
    "wind_nw": "North-West",

    # --- Days of week ---
    "day_today": "Today",
    "day_tomorrow": "Tomorrow",
    "weekday_0": "Monday",
    "weekday_1": "Tuesday",
    "weekday_2": "Wednesday",
    "weekday_3": "Thursday",
    "weekday_4": "Friday",
    "weekday_5": "Saturday",
    "weekday_6": "Sunday",

    # --- Weather conditions ---
    "weather_clear": "Clear sky",
    "weather_mostly_clear": "Mostly clear",
    "weather_partly_cloudy": "Partly cloudy",
    "weather_cloudy": "Overcast",
    "weather_fog": "Fog",
    "weather_depositing_rime_fog": "Rime fog",
    "weather_light_drizzle": "Light drizzle",
    "weather_moderate_drizzle": "Moderate drizzle",
    "weather_dense_drizzle": "Dense drizzle",
    "weather_slight_rain": "Slight rain",
    "weather_moderate_rain": "Rain",
    "weather_heavy_rain": "Heavy rain",
    "weather_slight_snow": "Slight snow",
    "weather_moderate_snow": "Snow",
    "weather_heavy_snow": "Heavy snow",
    "weather_snow_grains": "Snow grains",
    "weather_slight_showers": "Light rain showers",
    "weather_moderate_showers": "Showers",
    "weather_violent_showers": "Violent showers",
    "weather_snow_showers": "Snow showers",
    "weather_heavy_snow_showers": "Heavy snow showers",
    "weather_thunderstorm": "Thunderstorm",
    "weather_thunderstorm_slight_hail": "Thunderstorm with slight hail",
    "weather_thunderstorm_heavy_hail": "Thunderstorm with heavy hail",

    # --- Smart tips ---
    "weather_tip_rain": "• Rain is expected today. Don't forget your umbrella! 🌧",
    "weather_tip_snow": "• Snow expected. Dress warmly and stay safe on the roads! ❄️",
    "weather_tip_cold": "• It is rather cold outside. Dress warmly to stay healthy! 🧥",
    "weather_tip_hot": "• Hot weather. Drink plenty of water and stay in the shade! 🥤",
    "weather_tip_pleasant": "• Weather is very pleasant. Great time for a walk outdoors! 🌿",
    # --- Alerts ---
    "alert_message": (
        "🔴 <b>Alert: Hazardous air quality in {district}!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 AQI: <b>{aqi}</b> · PM2.5: {pm25} µg/m³\n\n"
        "💡 <b>Recommendations:</b>\n"
        "{advice}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ <i>You can turn off this alert in «🔔 Alerts».</i>"
    ),
    "digest_message": (
        "☀️ <b>Good morning!</b>\n"
        "📍 District: <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Status: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "💡 <b>Recommendations:</b>\n"
        "{advice}"
    ),
    "digest_message_weather": (
        "☀️ <b>Good morning!</b>\n"
        "📍 District: <b>{district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} Weather today: <b>{temp}°C</b> <i>({weather_desc})</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Air quality: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "💡 <b>Recommendations:</b>\n"
        "{advice}"
        "{switch_hint}"
    ),
    "digest_message_weather_home": (
        "☀️ <b>Good morning!</b>\n"
        "🏠 <b>Home district: {district}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{weather_emoji} Weather today: <b>{temp}°C</b> <i>({weather_desc})</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{emoji} Air quality: <b>{level}</b>\n"
        "📊 AQI: <b>{aqi}</b>\n\n"
        "💡 <b>Recommendations:</b>\n"
        "{advice}"
        "{switch_hint}"
    ),
    "digest_switch_hint": (
        "\n\n📍 <i>To view weather for your visited location ({other_district}), tap the button below.</i>"
    ),
    "settings_title": "🔔 <b>Alerts & Settings</b>\nHazardous air alerts, morning digest, and home district settings:",
    "toggle_alert": "🚨 Hazardous air alert: {state}",
    "toggle_digest": "☀️ Morning digest: {state}",
    "toggle_time": "⏰ Digest time: {time}",
    "toggle_home": "🏠 Home district: {name}",
    "choose_digest_time": "⏰ Choose morning digest time (Tashkent timezone):",
    "digest_time_set": "✅ Morning digest time set to: <b>{time}</b>",
    "home_title": (
        "🏠 <b>Home District Settings</b>\n\n"
        "Even when traveling to another city or district, your morning digests and "
        "hazardous air alerts will always be sent for your Home district.\n\n"
        "Current home district: <b>{name}</b>"
    ),
    "btn_set_current_as_home": "🏠 Set current ({name}) as home",
    "btn_choose_from_list": "🏙 Choose from list",
    "btn_clear_home": "❌ Reset home district",
    "btn_back": "⬅️ Back",
    "home_district_set": "✅ Home district saved: <b>{name}</b>",
    "home_district_cleared": "Home district reset.",
    "btn_switch_to_home": "🏠 {name} (Home)",
    "btn_switch_to_other": "📍 {name}",
    "btn_all_districts": "🏙 Other districts",
    "my_district_info": (
        "📍 Current district: <b>{current}</b>\n"
        "🏠 Home district: <b>{home}</b>\n\n"
        "To change, share your location or choose an option below:"
    ),
    "btn_set_home_prompt": "🏠 Save this district as home",
    "state_on": "enabled ✅",
    "state_off": "disabled ❌",
    # --- Complaints / Reports ---
    "cmp_limit": (
        "You can submit a maximum of {limit} reports per day. "
        "Please try again tomorrow."
    ),
    "cmp_choose_category": "📝 <b>Report</b>\n1/4 — Select report category:",
    "cat_burning": "🔥 Waste / leaf burning",
    "cat_industrial": "🏭 Industrial emission",
    "cat_smoke_dust": "💨 Smoke / dust",
    "cat_transport": "🚗 Vehicle emissions",
    "cat_tree_cutting": "🌳 Illegal tree cutting",
    "cat_other": "❓ Other",
    "cmp_send_photo": "2/4 — Send a photo of the incident (optional).",
    "cmp_photo_expected": "Please send a photo or click «Skip».",
    "cmp_send_location": (
        "3/4 — Send the incident location (via «📍 Send location» button). "
        "If exact location is unknown, you can use your district center."
    ),
    "cmp_location_expected": "Please send a location using the button below.",
    "cmp_write_text": "4/4 — Write a brief description (5 to 1000 characters).",
    "cmp_text_invalid": "Description must be between 5 and 1000 characters. Please write again.",
    "cmp_confirm": (
        "📋 <b>Review report</b>\n\n"
        "Category: {category}\n"
        "District: {district}\n"
        "Location: {location}\n"
        "Photo: {photo}\n\n"
        "Description: {text}"
    ),
    "loc_exact": "exact location",
    "loc_approx": "district center (approximate)",
    "photo_yes": "attached",
    "photo_no": "none",
    "cmp_saved": "✅ Your report <b>#{id}</b> has been received. Thank you!",
    "cmp_error": "An error occurred while saving the report. Please try again later.",
    "cmp_session_expired": "Report session expired. Please start again.",
}
