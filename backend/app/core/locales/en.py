"""English texts. Sent in HTML parse_mode. Curly braces only for {name} placeholders."""

TEXTS: dict[str, str] = {
    # --- General ---
    "choose_language": "Tilni tanlang / Выберите язык / Choose language",
    "lang_set": "✅ Language changed: English",
    "welcome": (
        "Hello! 👋\n"
        "This bot shows air quality in Tashkent, provides health recommendations, "
        "and allows submitting reports regarding air pollution."
    ),
    "welcome_back": "Welcome back! Please select an option from the menu below.",
    "menu_hint": "Please use the menu below.",
    "cancelled": "Cancelled.",
    # --- Buttons ---
    "btn_air": "🌫 Air quality",
    "btn_complaint": "📝 Submit complaint",
    "btn_alerts": "🔔 Alerts",
    "btn_district": "📍 My district",
    "btn_language": "🌐 Language",
    "btn_refresh": "🔄 Refresh",
    "btn_other_district": "📍 Other district",
    "btn_cancel": "❌ Cancel",
    "btn_skip": "⏭ Skip",
    "btn_confirm": "✅ Submit",
    "btn_send_location": "📍 Send location",
    "btn_choose_list": "🏙 Choose from list",
    "btn_use_my_district": "📍 Use my district center",
    "btn_other_region": "Other region ➡️",
    "btn_back_city": "⬅️ Tashkent city",
    # --- District selection ---
    "ask_district": (
        "📍 Send your location or choose from the list to determine your district.\n\n"
        "Location is only used to find the nearest district and is not stored."
    ),
    "choose_district": "Choose district:",
    "district_set": "✅ District saved: <b>{name}</b>",
    "district_detected": "✅ District detected: <b>{name}</b>",
    "district_not_found": "Could not determine district from your location. Please choose from the list.",
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
    "air_stale": "\n\n⚠️ <i>Fresh data could not be retrieved; showing the latest recorded reading.</i>",
    "air_unavailable": "Air quality data is currently unavailable. Please try again shortly.",
    "air_not_updated": "Data is not updated yet",
    "pick_district_view": "Which district's air quality would you like to view?",
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
    "settings_title": "🔔 <b>Alerts & Notifications</b>\nSettings for hazardous air alerts and morning digest:",
    "toggle_alert": "🚨 Hazardous air alert: {state}",
    "toggle_digest": "☀️ Morning digest: {state}",
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
