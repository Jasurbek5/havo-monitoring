"""Telegram Mini App API va HTML routeri."""

from collections import defaultdict
import html
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.i18n import DEFAULT_LANG
from app.core.memory_cache import get_memory_cache
from app.db.session import get_session_factory
from app.models import District, DistrictKind, User
from app.services.air_quality import build_provider
from app.services.districts import get_district, list_districts
from app.services.miniapp import get_miniapp_full_data

log = logging.getLogger(__name__)

miniapp_router = APIRouter(tags=["miniapp"])


@miniapp_router.get("/api/miniapp/districts")
async def get_miniapp_districts(lang: str = "uz") -> JSONResponse:
    """Mini App hudud tanlash modali uchun barcha hududlar ro'yxati."""
    async with get_session_factory()() as session:
        all_dists = await list_districts(session)

    city_dists = []
    region_dists = []
    other_dists = []

    for d in all_dists:
        item = {
            "id": d.id,
            "name": d.name(lang),
            "slug": d.slug,
            "lat": d.lat,
            "lon": d.lon,
        }
        if d.kind == DistrictKind.CITY_DISTRICT:
            city_dists.append(item)
        elif d.kind == DistrictKind.REGION:
            region_dists.append(item)
        else:
            other_dists.append(item)

    return JSONResponse({
        "city": sorted(city_dists, key=lambda x: x["name"]),
        "regions": sorted(region_dists, key=lambda x: x["name"]),
        "other": sorted(other_dists, key=lambda x: x["name"]),
    })


@miniapp_router.get("/api/miniapp/data")
async def get_miniapp_data(
    request: Request,
    district_id: int | None = Query(default=None),
    telegram_id: int | None = Query(default=None),
    lang: str = Query(default="uz"),
) -> JSONResponse:
    """Mini App uchun to'liq ma'lumotlar to'plami (Havo + Ob-havo + Soatlik + Haftalik)."""
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    redis = getattr(request.app.state, "redis", None) or (get_memory_cache() if settings.lite_mode else None)
    provider = build_provider(settings)

    if lang not in ("uz", "ru", "en"):
        lang = "uz"

    async with get_session_factory()() as session:
        target_district: District | None = None

        if district_id is not None:
            target_district = await get_district(session, district_id)

        if target_district is None and telegram_id is not None:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user:
                target_district = user.district or user.home_district
                if not lang and user.language:
                    lang = user.language

        # Agar hali ham topilmasa, Chilonzor (id 2) yoki birinchi tumanni tanlaymiz
        if target_district is None:
            target_district = await session.scalar(
                select(District).where(District.slug == "chilonzor")
            )
            if target_district is None:
                target_district = await session.scalar(select(District).order_by(District.id))

        if target_district is None:
            raise HTTPException(status_code=404, detail="Hududlar topilmadi")

        data = await get_miniapp_full_data(
            session=session,
            redis=redis,
            provider=provider,
            settings=settings,
            district=target_district,
            lang=lang,
        )

    await provider.aclose()
    return JSONResponse(data)


@miniapp_router.get("/app", response_class=HTMLResponse)
@miniapp_router.get("/miniapp", response_class=HTMLResponse)
async def serve_miniapp_html(request: Request) -> HTMLResponse:
    """Apple Weather uslubidagi zamonaviy Telegram Mini App bosh sahifasi."""
    html_content = _build_miniapp_html()
    return HTMLResponse(content=html_content)


def _build_miniapp_html() -> str:
    """Mini App bitta yaxlit HTML/CSS/JS sahifa sifatida (Render va Telegram uchun maksimal tezkor)."""
    return r"""<!DOCTYPE html>
<html lang="uz" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Havo & Ob-havo</title>
    <!-- Telegram WebApp SDK -->
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Google Fonts: Inter / SF Pro style -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">

    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'sans-serif'],
                    },
                    colors: {
                        ios: {
                            blue: '#0284c7',
                            card: 'rgba(255, 255, 255, 0.1)',
                            cardDark: 'rgba(15, 23, 42, 0.55)',
                            border: 'rgba(255, 255, 255, 0.15)',
                        }
                    }
                }
            }
        }
    </script>

    <style>
        * {
            -webkit-tap-highlight-color: transparent;
            user-select: none;
        }
        body {
            font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
            transition: background 0.7s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 100vh;
            overflow-x: hidden;
        }
        .glass-card {
            background: rgba(255, 255, 255, 0.12);
            backdrop-filter: blur(28px);
            -webkit-backdrop-filter: blur(28px);
            border: 1px solid rgba(255, 255, 255, 0.18);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.18);
            border-radius: 1.5rem;
        }
        .glass-pill {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.25);
        }
        .hide-scrollbar::-webkit-scrollbar {
            display: none;
        }
        .hide-scrollbar {
            -ms-overflow-style: none;
            scrollbar-width: none;
        }
        /* Dynamic Weather Themes */
        .theme-clear-day {
            background: radial-gradient(circle at 50% 10%, #38bdf8 0%, #0284c7 45%, #0369a1 100%);
        }
        .theme-clear-night {
            background: radial-gradient(circle at 50% 15%, #1e1b4b 0%, #0f172a 50%, #020617 100%);
        }
        .theme-clouds {
            background: radial-gradient(circle at 50% 10%, #64748b 0%, #475569 50%, #1e293b 100%);
        }
        .theme-rain {
            background: radial-gradient(circle at 50% 10%, #334155 0%, #1e293b 50%, #0f172a 100%);
        }
        .theme-fog {
            background: radial-gradient(circle at 50% 10%, #71717a 0%, #52525b 50%, #27272a 100%);
        }
        @keyframes pulse-soft {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.04); opacity: 0.9; }
        }
        .pulse-soft {
            animation: pulse-soft 3s ease-in-out infinite;
        }
        @keyframes spin-once {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        .spin-anim {
            animation: spin-once 0.6s ease-in-out;
        }
    </style>
</head>
<body class="theme-clear-day text-white antialiased pb-12 transition-all">

    <!-- Ambient Glow FX -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div id="ambientGlow" class="absolute -top-32 left-1/2 -translate-x-1/2 w-96 h-96 bg-white/20 rounded-full blur-3xl transition-all duration-1000"></div>
    </div>

    <!-- Main Container -->
    <div class="relative z-10 max-w-md mx-auto px-4 pt-3 flex flex-col gap-4">

        <!-- Top Navigation Bar -->
        <header class="flex items-center justify-between pt-1">
            <!-- District Selector Button -->
            <button onclick="openDistrictModal()" class="glass-pill px-3.5 py-1.5 rounded-full flex items-center gap-2 active:scale-95 transition text-sm font-semibold shadow-sm">
                <span class="text-base">📍</span>
                <span id="currentDistrictName">Yuklanmoqda...</span>
                <svg class="w-4 h-4 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
            </button>

            <!-- Actions: Lang Switcher & Refresh -->
            <div class="flex items-center gap-2">
                <!-- Lang Selector -->
                <div class="glass-pill rounded-full p-0.5 flex text-xs font-bold">
                    <button onclick="changeLang('uz')" id="langBtnUz" class="px-2.5 py-1 rounded-full transition bg-white/30 text-white">UZ</button>
                    <button onclick="changeLang('ru')" id="langBtnRu" class="px-2.5 py-1 rounded-full transition text-white/70">RU</button>
                    <button onclick="changeLang('en')" id="langBtnEn" class="px-2.5 py-1 rounded-full transition text-white/70">EN</button>
                </div>

                <!-- Refresh Button -->
                <button onclick="refreshData()" id="refreshBtn" class="glass-pill w-8 h-8 rounded-full flex items-center justify-center active:scale-90 transition">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                </button>
            </div>
        </header>

        <!-- Hero Weather Section -->
        <section class="text-center pt-2 pb-1 flex flex-col items-center">
            <div id="weatherEmojiHero" class="text-6xl mb-1 filter drop-shadow-md select-none transform hover:scale-110 transition duration-300">☀️</div>
            <h1 id="weatherTemp" class="text-7xl font-extrabold tracking-tight drop-shadow-sm font-sans flex items-start justify-center">
                <span>--</span><span class="text-4xl font-normal mt-1 text-white/80">°</span>
            </h1>
            <p id="weatherCondition" class="text-xl font-medium mt-0.5 text-white/90">Yuklanmoqda...</p>
            <div class="flex items-center gap-3 text-sm font-medium mt-1 text-white/80">
                <span id="tempRange">Maks: --° • Min: --°</span>
                <span>•</span>
                <span id="feelsLike">Tuyulishi: --°</span>
            </div>
        </section>

        <!-- AQI (Air Quality Index) Apple Card -->
        <section class="glass-card p-5 relative overflow-hidden">
            <div class="flex items-center justify-between pb-3 border-b border-white/10">
                <div class="flex items-center gap-2">
                    <span class="text-lg">🍃</span>
                    <span class="text-xs uppercase tracking-wider font-bold text-white/80" id="tAqiTitle">Havo Sifati (AQI)</span>
                </div>
                <span id="aqiUpdatedTime" class="text-xs font-mono text-white/60">--:--</span>
            </div>

            <!-- Gauge and Big AQI Number -->
            <div class="flex items-center justify-between pt-4 pb-2">
                <div class="flex flex-col">
                    <div class="flex items-baseline gap-2">
                        <span id="aqiNumber" class="text-5xl font-black tracking-tight font-sans">--</span>
                        <span id="aqiLevelBadge" class="text-sm font-bold px-3 py-1 rounded-full uppercase tracking-wide bg-emerald-500/30 text-emerald-300 border border-emerald-400/30">
                            Yuklanmoqda
                        </span>
                    </div>
                    <p id="aqiAdviceText" class="text-xs text-white/80 mt-2 leading-relaxed max-w-[210px]">
                        Havo ma'lumotlari tahlil qilinmoqda...
                    </p>
                </div>

                <!-- Circular Visual Barometer -->
                <div class="relative w-24 h-24 flex items-center justify-center">
                    <svg class="w-24 h-24 transform -rotate-90" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="40" stroke="rgba(255,255,255,0.15)" stroke-width="8" fill="none" stroke-linecap="round"></circle>
                        <circle id="aqiProgressCircle" cx="50" cy="50" r="40" stroke="#22c55e" stroke-width="9" fill="none" stroke-linecap="round" stroke-dasharray="251.2" stroke-dashoffset="251.2" class="transition-all duration-1000 ease-out"></circle>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                        <span id="aqiGaugeCenterEmoji" class="text-2xl">🟢</span>
                        <span class="text-[9px] uppercase font-bold text-white/60 mt-0.5">AQI</span>
                    </div>
                </div>
            </div>

            <!-- Pollutant Breakdown (PM2.5 and PM10) -->
            <div class="grid grid-cols-2 gap-2.5 mt-3 pt-3 border-t border-white/10 text-xs">
                <div class="bg-black/15 rounded-xl p-2.5 flex items-center justify-between">
                    <div>
                        <div class="text-white/60 font-semibold">PM2.5</div>
                        <div id="valPm25" class="text-base font-bold text-white mt-0.5">-- <span class="text-[10px] text-white/60 font-normal">µg/m³</span></div>
                    </div>
                    <span class="text-xs px-2 py-0.5 rounded-md bg-white/10 text-white/80" id="badgePm25">EPA standard</span>
                </div>
                <div class="bg-black/15 rounded-xl p-2.5 flex items-center justify-between">
                    <div>
                        <div class="text-white/60 font-semibold">PM10</div>
                        <div id="valPm10" class="text-base font-bold text-white mt-0.5">-- <span class="text-[10px] text-white/60 font-normal">µg/m³</span></div>
                    </div>
                    <span class="text-xs px-2 py-0.5 rounded-md bg-white/10 text-white/80" id="badgePm10">EPA standard</span>
                </div>
            </div>
        </section>

        <!-- 24-Hour Forecast (Hourly) -->
        <section class="glass-card p-4">
            <div class="flex items-center gap-2 pb-3 mb-1 text-xs uppercase tracking-wider font-bold text-white/80 border-b border-white/10">
                <span>⏰</span>
                <span id="tHourlyTitle">24 Soatlik Prognoz</span>
            </div>
            <!-- Horizontal Carousel -->
            <div id="hourlyContainer" class="flex items-center gap-3 overflow-x-auto hide-scrollbar pt-2 pb-1 scroll-smooth">
                <!-- Skeleton loader -->
                <div class="flex gap-3">
                    <div class="w-16 h-24 bg-white/10 rounded-2xl animate-pulse"></div>
                    <div class="w-16 h-24 bg-white/10 rounded-2xl animate-pulse"></div>
                    <div class="w-16 h-24 bg-white/10 rounded-2xl animate-pulse"></div>
                    <div class="w-16 h-24 bg-white/10 rounded-2xl animate-pulse"></div>
                </div>
            </div>
        </section>

        <!-- 7-Day Weekly Forecast -->
        <section class="glass-card p-4">
            <div class="flex items-center gap-2 pb-3 mb-2 text-xs uppercase tracking-wider font-bold text-white/80 border-b border-white/10">
                <span>📅</span>
                <span id="tWeeklyTitle">7 Kunlik Prognoz</span>
            </div>
            <div id="weeklyContainer" class="flex flex-col divide-y divide-white/10">
                <!-- Skeleton -->
                <div class="py-2.5 flex justify-between animate-pulse"><div class="w-16 h-4 bg-white/10 rounded"></div><div class="w-32 h-4 bg-white/10 rounded"></div></div>
                <div class="py-2.5 flex justify-between animate-pulse"><div class="w-16 h-4 bg-white/10 rounded"></div><div class="w-32 h-4 bg-white/10 rounded"></div></div>
                <div class="py-2.5 flex justify-between animate-pulse"><div class="w-16 h-4 bg-white/10 rounded"></div><div class="w-32 h-4 bg-white/10 rounded"></div></div>
            </div>
        </section>

        <!-- Bento Grid Details (iOS Weather Widgets) -->
        <section class="grid grid-cols-2 gap-3">
            <!-- Wind -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>💨</span> <span id="tWindTitle">Shamol</span>
                </div>
                <div>
                    <div class="text-2xl font-bold font-sans"><span id="valWindSpeed">--</span> <span class="text-xs font-normal text-white/70">m/s</span></div>
                    <div id="valWindDir" class="text-xs text-white/80 mt-1 truncate">Shimoliy</div>
                </div>
                <div class="text-[11px] text-white/60 flex items-center justify-between">
                    <span>Kompas:</span>
                    <span id="valWindCompass" class="font-mono text-white/90">--°</span>
                </div>
            </div>

            <!-- Humidity -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>💧</span> <span id="tHumidityTitle">Namlik</span>
                </div>
                <div>
                    <div class="text-2xl font-bold font-sans"><span id="valHumidity">--</span><span class="text-sm font-normal text-white/70">%</span></div>
                    <div id="valHumidityComfort" class="text-xs text-white/80 mt-1">Qulay darajada</div>
                </div>
                <div class="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
                    <div id="barHumidity" class="bg-sky-400 h-full rounded-full transition-all duration-700" style="width: 50%;"></div>
                </div>
            </div>

            <!-- UV Index -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>☀️</span> <span id="tUvTitle">UV Indeksi</span>
                </div>
                <div>
                    <div class="text-2xl font-bold font-sans" id="valUv">--</div>
                    <div id="valUvDesc" class="text-xs text-white/80 mt-1">O'rtacha xavf</div>
                </div>
                <div class="w-full bg-gradient-to-r from-green-400 via-yellow-400 to-violet-500 h-1.5 rounded-full"></div>
            </div>

            <!-- Sun (Sunrise & Sunset) -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>🌅</span> <span id="tSunTitle">Quyosh</span>
                </div>
                <div class="flex justify-between items-center text-xs">
                    <div>
                        <div class="text-white/60 text-[10px]">Chiqishi</div>
                        <div id="valSunrise" class="font-bold text-white mt-0.5">--:--</div>
                    </div>
                    <div class="text-right">
                        <div class="text-white/60 text-[10px]">Botishi</div>
                        <div id="valSunset" class="font-bold text-white mt-0.5">--:--</div>
                    </div>
                </div>
                <!-- Sun Position Track -->
                <div class="relative w-full bg-white/10 h-1.5 rounded-full mt-1">
                    <div id="sunPosDot" class="absolute -top-1 w-3.5 h-3.5 bg-amber-300 rounded-full shadow-md transition-all duration-700" style="left: 50%;"></div>
                </div>
            </div>

            <!-- Pressure -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>⏱</span> <span id="tPressureTitle">Bosim</span>
                </div>
                <div>
                    <div class="text-2xl font-bold font-sans"><span id="valPressureMmhg">--</span> <span class="text-xs font-normal text-white/70">mmHg</span></div>
                    <div id="valPressureHpa" class="text-xs text-white/80 mt-1">-- hPa</div>
                </div>
                <div class="text-[11px] text-white/60">Normal atmosfera</div>
            </div>

            <!-- App Info / Telegram Bot -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>📱</span> <span>Havo Bot</span>
                </div>
                <div>
                    <div class="text-sm font-bold">Toshkent & Viloyatlar</div>
                    <div class="text-[11px] text-white/70 mt-1">Real vaqt monitoringi</div>
                </div>
                <button onclick="closeMiniApp()" class="w-full py-1.5 rounded-xl bg-white/20 active:scale-95 transition text-xs font-bold text-center">
                    Yopish ✕
                </button>
            </div>
        </section>

    </div>

    <!-- District Selector Drawer / Modal -->
    <div id="districtModal" class="fixed inset-0 z-50 bg-black/60 backdrop-blur-md hidden opacity-0 transition-opacity duration-300 flex items-end sm:items-center justify-center p-0 sm:p-4">
        <div id="districtModalCard" class="w-full max-w-md bg-slate-900 border border-white/20 rounded-t-3xl sm:rounded-3xl p-5 max-h-[85vh] flex flex-col transform translate-y-full transition-transform duration-300 shadow-2xl">
            <!-- Modal Header -->
            <div class="flex items-center justify-between pb-3 border-b border-white/10">
                <div class="flex items-center gap-2">
                    <span class="text-xl">🏙</span>
                    <h3 class="text-base font-bold" id="tChooseDistrictModal">Hududni tanlang</h3>
                </div>
                <button onclick="closeDistrictModal()" class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90 transition">✕</button>
            </div>

            <!-- Search Input -->
            <div class="pt-3 pb-2">
                <input type="text" id="districtSearchInput" oninput="filterDistricts()" placeholder="Qidirish (masalan: Chilonzor, Samarqand)..." class="w-full bg-white/10 border border-white/15 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/40 focus:outline-none focus:border-sky-400 transition">
            </div>

            <!-- Tabs: Toshkent / Viloyatlar -->
            <div class="flex gap-2 pt-1 pb-3 text-xs font-bold">
                <button onclick="switchDistrictTab('city')" id="tabCityBtn" class="flex-1 py-1.5 rounded-lg bg-sky-600 text-white transition">Toshkent tumanlari (12)</button>
                <button onclick="switchDistrictTab('regions')" id="tabRegionBtn" class="flex-1 py-1.5 rounded-lg bg-white/10 text-white/70 transition">Viloyatlar (13)</button>
            </div>

            <!-- Districts List -->
            <div id="districtListScroll" class="flex-1 overflow-y-auto hide-scrollbar flex flex-col gap-1.5 py-1">
                <!-- Dynamically populated -->
            </div>
        </div>
    </div>

    <!-- Frontend Application Logic -->
    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
            tg.setHeaderColor('#0284c7');
            tg.setBackgroundColor('#0369a1');
        }

        let currentLang = 'uz';
        let currentDistrictId = 2; // Default Chilonzor
        let allDistricts = { city: [], regions: [], other: [] };
        let currentTab = 'city';

        // Auto detect language from Telegram
        const userTgLang = tg?.initDataUnsafe?.user?.language_code;
        if (userTgLang) {
            if (userTgLang.startsWith('ru')) currentLang = 'ru';
            else if (userTgLang.startsWith('en')) currentLang = 'en';
            else currentLang = 'uz';
        }

        // Translations Dictionary for UI Strings
        const I18N = {
            uz: {
                aqiTitle: "Havo Sifati (AQI)",
                hourlyTitle: "24 Soatlik Prognoz",
                weeklyTitle: "7 Kunlik Prognoz",
                windTitle: "Shamol",
                humidityTitle: "Namlik",
                uvTitle: "UV Indeksi",
                sunTitle: "Quyosh",
                pressureTitle: "Bosim",
                chooseModal: "Hududni tanlang",
                searchPlaceholder: "Qidirish (masalan: Chilonzor, Samarqand)...",
                tabCity: "Toshkent tumanlari",
                tabRegions: "Viloyatlar",
                comfortHumid: "Qulay darajada",
                close: "Yopish ✕",
            },
            ru: {
                aqiTitle: "Качество Воздуха (AQI)",
                hourlyTitle: "Прогноз на 24 Часа",
                weeklyTitle: "Прогноз на 7 Дней",
                windTitle: "Ветер",
                humidityTitle: "Влажность",
                uvTitle: "УФ-Индекс",
                sunTitle: "Солнце",
                pressureTitle: "Давление",
                chooseModal: "Выберите район",
                searchPlaceholder: "Поиск (например: Чиланзар, Самарканд)...",
                tabCity: "Районы Ташкента",
                tabRegions: "Области",
                comfortHumid: "Комфортная влажность",
                close: "Закрыть ✕",
            },
            en: {
                aqiTitle: "Air Quality (AQI)",
                hourlyTitle: "24-Hour Forecast",
                weeklyTitle: "7-Day Forecast",
                windTitle: "Wind",
                humidityTitle: "Humidity",
                uvTitle: "UV Index",
                sunTitle: "Sun Position",
                pressureTitle: "Pressure",
                chooseModal: "Choose District",
                searchPlaceholder: "Search (e.g. Chilanzar, Samarkand)...",
                tabCity: "Tashkent Districts",
                tabRegions: "Regions",
                comfortHumid: "Comfortable",
                close: "Close ✕",
            }
        };

        function haptic(type = 'light') {
            try {
                if (tg?.HapticFeedback) {
                    tg.HapticFeedback.impactOccurred(type);
                }
            } catch(e) {}
        }

        function updateStaticTexts() {
            const t = I18N[currentLang] || I18N.uz;
            document.getElementById('tAqiTitle').textContent = t.aqiTitle;
            document.getElementById('tHourlyTitle').textContent = t.hourlyTitle;
            document.getElementById('tWeeklyTitle').textContent = t.weeklyTitle;
            document.getElementById('tWindTitle').textContent = t.windTitle;
            document.getElementById('tHumidityTitle').textContent = t.humidityTitle;
            document.getElementById('tUvTitle').textContent = t.uvTitle;
            document.getElementById('tSunTitle').textContent = t.sunTitle;
            document.getElementById('tPressureTitle').textContent = t.pressureTitle;
            document.getElementById('tChooseDistrictModal').textContent = t.chooseModal;
            document.getElementById('districtSearchInput').placeholder = t.searchPlaceholder;
            document.getElementById('tabCityBtn').textContent = `${t.tabCity} (${allDistricts.city?.length || 12})`;
            document.getElementById('tabRegionBtn').textContent = `${t.tabRegions} (${allDistricts.regions?.length || 13})`;

            // Active lang button highlight
            ['uz', 'ru', 'en'].forEach(l => {
                const b = document.getElementById('langBtn' + l.charAt(0).toUpperCase() + l.slice(1));
                if (b) {
                    if (l === currentLang) {
                        b.className = "px-2.5 py-1 rounded-full transition bg-white/30 text-white font-bold";
                    } else {
                        b.className = "px-2.5 py-1 rounded-full transition text-white/70 hover:text-white";
                    }
                }
            });
        }

        function setWeatherTheme(weatherCode, isNight = false) {
            const body = document.body;
            body.className = body.className.replace(/theme-[a-z\-]+/g, '').trim();

            if (isNight) {
                body.classList.add('theme-clear-night');
                tg?.setHeaderColor?.('#0f172a');
                return;
            }

            if ([0, 1].includes(weatherCode)) {
                body.classList.add('theme-clear-day');
                tg?.setHeaderColor?.('#0284c7');
            } else if ([2, 3].includes(weatherCode)) {
                body.classList.add('theme-clouds');
                tg?.setHeaderColor?.('#475569');
            } else if ([51, 53, 55, 61, 63, 65, 80, 81, 82, 95].includes(weatherCode)) {
                body.classList.add('theme-rain');
                tg?.setHeaderColor?.('#1e293b');
            } else {
                body.classList.add('theme-fog');
                tg?.setHeaderColor?.('#3f3f46');
            }
        }

        async function loadData() {
            const tgUser = tg?.initDataUnsafe?.user;
            const tgId = tgUser?.id || '';

            try {
                const res = await fetch(`/api/miniapp/data?district_id=${currentDistrictId}&lang=${currentLang}&telegram_id=${tgId}`);
                if (!res.ok) throw new Error("HTTP error " + res.status);
                const data = await res.json();
                renderUI(data);
            } catch (err) {
                console.error("MiniApp yuklashda xatolik:", err);
            }
        }

        function renderUI(data) {
            const { district, air, weather, hourly, weekly } = data;

            // 1. District
            document.getElementById('currentDistrictName').textContent = district.name;

            // 2. Weather Hero
            document.getElementById('weatherEmojiHero').textContent = weather.emoji || '☀️';
            document.getElementById('weatherTemp').innerHTML = `<span>${Math.round(weather.temp)}</span><span class="text-4xl font-normal mt-1 text-white/80">°</span>`;
            document.getElementById('weatherCondition').textContent = weather.condition;
            document.getElementById('tempRange').textContent = `Maks: ${Math.round(weather.temp_max)}° • Min: ${Math.round(weather.temp_min)}°`;
            document.getElementById('feelsLike').textContent = `Tuyulishi: ${Math.round(weather.feels_like)}°`;

            // Weather theme
            const nowH = new Date().getHours();
            const isNight = nowH < 6 || nowH >= 20;
            setWeatherTheme(weather.weather_code, isNight);

            // 3. AQI Card
            document.getElementById('aqiNumber').textContent = air.aqi;
            const badge = document.getElementById('aqiLevelBadge');
            badge.textContent = air.level_name;
            badge.style.backgroundColor = `${air.color}35`;
            badge.style.color = air.color;
            badge.style.borderColor = `${air.color}50`;

            document.getElementById('aqiAdviceText').textContent = air.advice;
            document.getElementById('aqiUpdatedTime').textContent = air.updated_at;
            document.getElementById('aqiGaugeCenterEmoji').textContent = air.emoji;

            // AQI circular stroke (max 300 AQI for full circle, 251.2 dasharray)
            const circle = document.getElementById('aqiProgressCircle');
            const percent = Math.min(1, air.aqi / 300);
            const offset = 251.2 - (percent * 251.2);
            circle.style.stroke = air.color;
            circle.style.strokeDashoffset = offset;

            // Pollutants
            document.getElementById('valPm25').innerHTML = `${air.pm2_5 !== null ? air.pm2_5 : '—'} <span class="text-[10px] text-white/60 font-normal">µg/m³</span>`;
            document.getElementById('valPm10').innerHTML = `${air.pm10 !== null ? air.pm10 : '—'} <span class="text-[10px] text-white/60 font-normal">µg/m³</span>`;

            // 4. Hourly Forecast
            const hourlyEl = document.getElementById('hourlyContainer');
            if (hourly && hourly.length > 0) {
                hourlyEl.innerHTML = hourly.map(item => `
                    <div class="flex-shrink-0 w-16 py-3 px-2 rounded-2xl flex flex-col items-center justify-between text-center transition ${item.is_now ? 'bg-white/25 border border-white/30 shadow-md' : 'bg-white/5'}">
                        <span class="text-[11px] font-semibold ${item.is_now ? 'text-white' : 'text-white/70'}">${item.is_now ? (currentLang === 'ru' ? 'Сейчас' : (currentLang === 'en' ? 'Now' : 'Hozir')) : item.time}</span>
                        <span class="text-2xl my-1.5 filter drop-shadow">${item.emoji}</span>
                        <span class="text-sm font-bold font-sans">${Math.round(item.temp)}°</span>
                        ${item.pop > 10 ? `<span class="text-[9px] font-bold text-sky-300 mt-1">💧${item.pop}%</span>` : ''}
                    </div>
                `).join('');
            }

            // 5. Weekly Forecast
            const weeklyEl = document.getElementById('weeklyContainer');
            if (weekly && weekly.length > 0) {
                // Find weekly min and max for proportional bars
                const allMin = Math.min(...weekly.map(d => d.temp_min));
                const allMax = Math.max(...weekly.map(d => d.temp_max));
                const range = Math.max(1, allMax - allMin);

                weeklyEl.innerHTML = weekly.map(day => {
                    const leftPct = Math.round(((day.temp_min - allMin) / range) * 100);
                    const widthPct = Math.max(12, Math.round(((day.temp_max - day.temp_min) / range) * 100));

                    return `
                    <div class="py-2.5 flex items-center justify-between text-xs font-medium">
                        <span class="w-16 font-semibold truncate ${day.day_name === 'Bugun' || day.day_name === 'Сегодня' || day.day_name === 'Today' ? 'text-sky-300 font-bold' : 'text-white'}">${day.day_name}</span>
                        <div class="w-8 text-center text-lg">${day.emoji}</div>
                        <span class="w-10 text-right font-mono text-white/70 font-bold">${Math.round(day.temp_min)}°</span>
                        <div class="flex-1 mx-3 h-1.5 bg-white/10 rounded-full relative overflow-hidden">
                            <div class="absolute h-full rounded-full bg-gradient-to-r from-sky-400 via-amber-300 to-orange-400" style="left: ${leftPct}%; width: ${widthPct}%;"></div>
                        </div>
                        <span class="w-10 text-right font-mono text-white font-bold">${Math.round(day.temp_max)}°</span>
                    </div>
                    `;
                }).join('');
            }

            // 6. Bento Grid Cards
            document.getElementById('valWindSpeed').textContent = weather.wind_speed;
            document.getElementById('valWindDir').textContent = weather.wind_dir;
            document.getElementById('valWindCompass').textContent = `${weather.wind_deg}°`;

            document.getElementById('valHumidity').textContent = weather.humidity;
            document.getElementById('barHumidity').style.width = `${weather.humidity}%`;

            document.getElementById('valUv').textContent = weather.uv_index;
            document.getElementById('valUvDesc').textContent = weather.uv_category;

            document.getElementById('valSunrise').textContent = weather.sunrise;
            document.getElementById('valSunset').textContent = weather.sunset;
            document.getElementById('sunPosDot').style.left = `${Math.min(95, Math.max(5, weather.sun_progress * 100))}%`;

            document.getElementById('valPressureMmhg').textContent = weather.pressure_mmhg;
            document.getElementById('valPressureHpa').textContent = `${weather.pressure_hpa} hPa`;
        }

        async function loadDistrictsList() {
            try {
                const res = await fetch(`/api/miniapp/districts?lang=${currentLang}`);
                allDistricts = await res.json();
                renderDistrictsList();
                updateStaticTexts();
            } catch(e) {
                console.error("Hududlar ro'yxatini yuklashda xatolik:", e);
            }
        }

        function renderDistrictsList() {
            const list = allDistricts[currentTab] || [];
            const search = (document.getElementById('districtSearchInput')?.value || '').toLowerCase().trim();
            const container = document.getElementById('districtListScroll');

            const filtered = list.filter(d => d.name.toLowerCase().includes(search));

            if (filtered.length === 0) {
                container.innerHTML = '<div class="text-center py-6 text-white/40 text-xs">Hudud topilmadi</div>';
                return;
            }

            container.innerHTML = filtered.map(d => `
                <button onclick="selectDistrict(${d.id})" class="w-full text-left p-3 rounded-xl flex items-center justify-between transition ${d.id === currentDistrictId ? 'bg-sky-600/40 border border-sky-400/50 font-bold' : 'bg-white/5 hover:bg-white/10 text-white/80'}">
                    <span>${d.name}</span>
                    ${d.id === currentDistrictId ? '<span class="text-sky-300">✓</span>' : '<span class="text-white/30 text-xs">Tanlash →</span>'}
                </button>
            `).join('');
        }

        function filterDistricts() {
            renderDistrictsList();
        }

        function switchDistrictTab(tab) {
            haptic('selection');
            currentTab = tab;
            const cityBtn = document.getElementById('tabCityBtn');
            const regBtn = document.getElementById('tabRegionBtn');

            if (tab === 'city') {
                cityBtn.className = "flex-1 py-1.5 rounded-lg bg-sky-600 text-white transition";
                regBtn.className = "flex-1 py-1.5 rounded-lg bg-white/10 text-white/70 transition";
            } else {
                cityBtn.className = "flex-1 py-1.5 rounded-lg bg-white/10 text-white/70 transition";
                regBtn.className = "flex-1 py-1.5 rounded-lg bg-sky-600 text-white transition";
            }
            renderDistrictsList();
        }

        function selectDistrict(id) {
            haptic('medium');
            currentDistrictId = id;
            closeDistrictModal();
            loadData();
        }

        function openDistrictModal() {
            haptic('light');
            const modal = document.getElementById('districtModal');
            const card = document.getElementById('districtModalCard');
            modal.classList.remove('hidden');
            setTimeout(() => {
                modal.classList.remove('opacity-0');
                card.classList.remove('translate-y-full');
            }, 10);
        }

        function closeDistrictModal() {
            haptic('light');
            const modal = document.getElementById('districtModal');
            const card = document.getElementById('districtModalCard');
            modal.classList.add('opacity-0');
            card.classList.add('translate-y-full');
            setTimeout(() => {
                modal.classList.add('hidden');
            }, 300);
        }

        function changeLang(lang) {
            haptic('selection');
            currentLang = lang;
            updateStaticTexts();
            loadDistrictsList();
            loadData();
        }

        function refreshData() {
            haptic('medium');
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('spin-anim');
            setTimeout(() => btn.classList.remove('spin-anim'), 650);
            loadData();
        }

        function closeMiniApp() {
            if (tg) {
                tg.close();
            } else {
                window.history.back();
            }
        }

        // Initialize on load
        window.addEventListener('DOMContentLoaded', () => {
            updateStaticTexts();
            loadDistrictsList();
            loadData();
        });
    </script>
</body>
</html>
"""
