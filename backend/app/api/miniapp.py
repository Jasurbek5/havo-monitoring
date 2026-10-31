"""Telegram Mini App API va HTML routeri."""

from collections import defaultdict
import html
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.i18n import DEFAULT_LANG
from app.core.memory_cache import get_memory_cache
from app.db.session import get_session_factory
from app.models import District, DistrictKind, User
from app.services.air_quality import build_provider
from app.services.districts import (
    get_district,
    get_or_create_district_by_location,
    list_districts,
)
from app.services.geocoding import LocationResult, search_locations
from app.services.miniapp import get_miniapp_full_data

log = logging.getLogger(__name__)

miniapp_router = APIRouter(tags=["miniapp"])


@miniapp_router.get("/api/miniapp/districts")
async def get_miniapp_districts(
    lang: str = "uz",
    telegram_id: int | None = Query(default=None),
) -> JSONResponse:
    """Mini App hudud tanlash modali uchun barcha hududlar ro'yxati (Oldindan kiritilganlar + Uy hududi)."""
    async with get_session_factory()() as session:
        all_dists = await list_districts(session)

        home_district_info = None
        if telegram_id:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user and user.home_district:
                home_district_info = {
                    "id": user.home_district.id,
                    "name": user.home_district.name(lang),
                }

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
        # Dinamik qidiruv orqali yaratilgan hududlar standart ro'yxatni ifloslantirmaydi
        if d.slug.startswith("loc-"):
            other_dists.append(item)
            continue

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
        "home": home_district_info,
    })


@miniapp_router.get("/api/miniapp/search")
async def search_districts_global(
    request: Request,
    q: str = Query(..., min_length=1),
    lang: str = Query(default="uz"),
) -> JSONResponse:
    """Butun dunyo bo'ylab shaharlar va hududlarni qidirish (Global Geocoding)."""
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    results = await search_locations(q, owm_api_key=settings.owm_api_key, limit=8)

    formatted = []
    for r in results:
        formatted.append({
            "name": r.display_name(lang),
            "name_uz": r.name_uz,
            "name_ru": r.name_ru,
            "name_en": r.name_en,
            "lat": r.lat,
            "lon": r.lon,
            "country": r.country,
            "admin_area": r.admin_area,
        })
    return JSONResponse(formatted)


class LocationSelectRequest(BaseModel):
    name_uz: str
    name_ru: str
    name_en: str
    lat: float
    lon: float
    country: str = ""
    admin_area: str = ""
    telegram_id: int | None = None


@miniapp_router.post("/api/miniapp/select-location")
async def select_location_district(
    body: LocationSelectRequest,
    lang: str = Query(default="uz"),
) -> JSONResponse:
    """Global qidiruvdan tanlangan joylashuvni District qilib olish yoki yaratish."""
    loc = LocationResult(
        name_uz=body.name_uz,
        name_ru=body.name_ru,
        name_en=body.name_en,
        lat=body.lat,
        lon=body.lon,
        country=body.country,
        admin_area=body.admin_area,
    )
    async with get_session_factory()() as session:
        district = await get_or_create_district_by_location(session, loc)

        if body.telegram_id:
            user = await session.scalar(select(User).where(User.telegram_id == body.telegram_id))
            if user:
                user.district_id = district.id
                await session.commit()

        return JSONResponse({
            "ok": True,
            "district": {
                "id": district.id,
                "name": district.name(lang),
                "lat": district.lat,
                "lon": district.lon,
            }
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


class UserSettingsUpdate(BaseModel):
    telegram_id: int
    alert_enabled: bool | None = None
    daily_digest: bool | None = None
    digest_time: str | None = None
    timezone: str | None = None
    home_district_id: int | None = None
    clear_home: bool = False


@miniapp_router.get("/api/miniapp/settings")
async def get_user_settings(
    telegram_id: int = Query(...),
    lang: str = Query(default="uz"),
) -> JSONResponse:
    """Foydalanuvchi sozlamalarini olish."""
    async with get_session_factory()() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            return JSONResponse({
                "telegram_id": telegram_id,
                "alert_enabled": True,
                "daily_digest": False,
                "digest_time": "07:00",
                "timezone": "auto",
                "home_district_id": None,
                "home_district_name": "—",
            })

        home_name = user.home_district.name(lang) if user.home_district else "—"
        return JSONResponse({
            "telegram_id": user.telegram_id,
            "alert_enabled": user.alert_enabled,
            "daily_digest": user.daily_digest,
            "digest_time": user.digest_time or "07:00",
            "timezone": getattr(user, "timezone", "auto") or "auto",
            "home_district_id": user.home_district_id,
            "home_district_name": home_name,
        })


@miniapp_router.post("/api/miniapp/settings")
async def update_user_settings(
    body: UserSettingsUpdate,
    lang: str = Query(default="uz"),
) -> JSONResponse:
    """Foydalanuvchi sozlamalarini yangilash."""
    async with get_session_factory()() as session:
        user = await session.scalar(select(User).where(User.telegram_id == body.telegram_id))
        if not user:
            user = User(
                telegram_id=body.telegram_id,
                language=lang,
                alert_enabled=body.alert_enabled if body.alert_enabled is not None else True,
                daily_digest=body.daily_digest if body.daily_digest is not None else False,
                digest_time=body.digest_time or "07:00",
                timezone=body.timezone or "auto",
            )
            session.add(user)
        else:
            if body.alert_enabled is not None:
                user.alert_enabled = body.alert_enabled
            if body.daily_digest is not None:
                user.daily_digest = body.daily_digest
            if body.digest_time is not None:
                user.digest_time = body.digest_time
            if body.timezone is not None:
                user.timezone = body.timezone
            if body.clear_home:
                user.home_district_id = None
            elif body.home_district_id is not None:
                user.home_district_id = body.home_district_id

        await session.commit()
        user = await session.scalar(select(User).where(User.telegram_id == body.telegram_id))
        home_name = user.home_district.name(lang) if (user and user.home_district) else "—"
        return JSONResponse({
            "ok": True,
            "settings": {
                "telegram_id": user.telegram_id if user else body.telegram_id,
                "alert_enabled": user.alert_enabled if user else True,
                "daily_digest": user.daily_digest if user else False,
                "digest_time": user.digest_time if user else "07:00",
                "timezone": getattr(user, "timezone", "auto") if user else "auto",
                "home_district_id": user.home_district_id if user else None,
                "home_district_name": home_name,
            }
        })


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
                <!-- Language Selector Dropdown -->
                <div class="relative" id="langMenuContainer">
                    <button onclick="toggleLangMenu(event)" id="langDropdownBtn" class="glass-pill px-3 py-1.5 rounded-full flex items-center gap-1.5 text-xs font-bold active:scale-95 transition shadow-sm">
                        <span id="currentLangFlag">🇺🇿</span>
                        <span id="currentLangLabel">UZ</span>
                        <svg class="w-3 h-3 opacity-70 transform transition-transform duration-200" id="langChevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>

                    <!-- Language Popup Dropdown -->
                    <div id="langDropdownMenu" class="absolute right-0 mt-1.5 w-36 bg-slate-900/95 border border-white/20 p-1.5 rounded-2xl hidden z-50 shadow-2xl backdrop-blur-2xl flex flex-col gap-0.5">
                        <button onclick="selectLang('uz')" class="flex items-center justify-between w-full px-2.5 py-1.5 rounded-xl text-xs font-semibold hover:bg-white/15 transition text-left">
                            <span class="flex items-center gap-2"><span>🇺🇿</span> <span>O'zbekcha</span></span>
                            <span id="checkUz" class="text-sky-300 font-bold">✓</span>
                        </button>
                        <button onclick="selectLang('ru')" class="flex items-center justify-between w-full px-2.5 py-1.5 rounded-xl text-xs font-semibold hover:bg-white/15 transition text-left">
                            <span class="flex items-center gap-2"><span>🇷🇺</span> <span>Русский</span></span>
                            <span id="checkRu" class="text-sky-300 font-bold hidden">✓</span>
                        </button>
                        <button onclick="selectLang('en')" class="flex items-center justify-between w-full px-2.5 py-1.5 rounded-xl text-xs font-semibold hover:bg-white/15 transition text-left">
                            <span class="flex items-center gap-2"><span>🇬🇧</span> <span>English</span></span>
                            <span id="checkEn" class="text-sky-300 font-bold hidden">✓</span>
                        </button>
                    </div>
                </div>

                <!-- Refresh Button -->
                <button onclick="refreshData()" id="refreshBtn" class="glass-pill w-8 h-8 rounded-full flex items-center justify-center active:scale-90 transition">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                </button>

                <!-- Settings Button (refresh o'ng tomonida) -->
                <button onclick="openSettingsModal()" id="settingsBtn" class="glass-pill w-8 h-8 rounded-full flex items-center justify-center active:scale-90 transition shadow-sm" title="Sozlamalar">
                    <svg class="w-4 h-4 text-white/90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    </svg>
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
                <div class="flex items-center gap-1.5 text-xs text-white/70">
                    <span id="lblUpdatedAt">Yangilangan:</span>
                    <span id="aqiUpdatedTime" class="font-mono text-white/90">--:--</span>
                </div>
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
                    <span id="lblCompass">Kompas:</span>
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
                        <div class="text-white/60 text-[10px]" id="lblSunrise">Chiqishi</div>
                        <div id="valSunrise" class="font-bold text-white mt-0.5">--:--</div>
                    </div>
                    <div class="text-right">
                        <div class="text-white/60 text-[10px]" id="lblSunset">Botishi</div>
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
                <div class="text-[11px] text-white/60" id="lblPressureDesc">Normal atmosfera</div>
            </div>

            <!-- App Info / Telegram Bot -->
            <div class="glass-card p-4 flex flex-col justify-between h-36">
                <div class="flex items-center gap-1.5 text-xs font-semibold text-white/70 uppercase">
                    <span>📱</span> <span id="botTitle">Havo Bot</span>
                </div>
                <div>
                    <div class="text-sm font-bold" id="botSubtitle">Toshkent & Viloyatlar</div>
                    <div class="text-[11px] text-white/70 mt-1" id="botDesc">Real vaqt monitoringi</div>
                </div>
                <button onclick="closeMiniApp()" id="btnClose" class="w-full py-1.5 rounded-xl bg-white/20 active:scale-95 transition text-xs font-bold text-center">
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

            <!-- Search Input with spinner -->
            <div class="pt-3 pb-2 relative">
                <input type="text" id="districtSearchInput" oninput="handleDistrictSearch(this.value)" placeholder="Qidirish (masalan: Chilonzor, Samarqand, Istanbul)..." class="w-full bg-white/10 border border-white/15 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/40 focus:outline-none focus:border-sky-400 transition pr-9">
                <div id="searchSpinner" class="absolute right-3 top-5 hidden">
                    <svg class="animate-spin h-4 w-4 text-sky-400" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
                </div>
            </div>

            <!-- Home District Banner (if user has home district) -->
            <div id="homeDistrictQuickCard" class="hidden mb-2">
                <button onclick="selectHomeDistrict()" class="w-full text-left p-2.5 rounded-2xl bg-gradient-to-r from-sky-600/30 to-indigo-600/30 border border-sky-400/40 flex items-center justify-between active:scale-98 transition shadow-sm">
                    <div class="flex items-center gap-2.5">
                        <span class="text-xl">🏠</span>
                        <div>
                            <div class="text-[10px] text-sky-300 font-bold uppercase tracking-wider" id="lblHomeDistrictBanner">Mening Uyim</div>
                            <div id="homeDistrictBannerName" class="text-sm font-bold text-white mt-0.5">Chilonzor</div>
                        </div>
                    </div>
                    <span class="text-xs px-2.5 py-1 rounded-full bg-sky-500/30 text-sky-200 border border-sky-400/30 font-semibold" id="lblSelectHomeBtn">Tanlash</span>
                </button>
            </div>

            <!-- Tabs: Toshkent / Viloyatlar (Visible when search is empty) -->
            <div id="districtTabsContainer" class="flex gap-2 pt-1 pb-2 text-xs font-bold">
                <button onclick="switchDistrictTab('city')" id="tabCityBtn" class="flex-1 py-1.5 rounded-lg bg-sky-600 text-white transition">Toshkent tumanlari</button>
                <button onclick="switchDistrictTab('regions')" id="tabRegionBtn" class="flex-1 py-1.5 rounded-lg bg-white/10 text-white/70 transition">Viloyatlar</button>
            </div>

            <!-- Search Mode Header (Visible when searching) -->
            <div id="searchSectionHeader" class="hidden text-[11px] font-bold text-white/60 uppercase tracking-wider pb-1 pt-1 flex items-center justify-between">
                <span id="lblSearchResultsTitle">Qidiruv natijalari</span>
                <span id="lblGlobalSearchBadge" class="text-[10px] text-sky-400 font-normal">Global qidiruv</span>
            </div>

            <!-- Districts List -->
            <div id="districtListScroll" class="flex-1 overflow-y-auto hide-scrollbar flex flex-col gap-1.5 py-1">
                <!-- Dynamically populated -->
            </div>
        </div>
    </div>

    <!-- Settings Modal / Drawer -->
    <div id="settingsModal" class="fixed inset-0 z-50 bg-black/60 backdrop-blur-md hidden opacity-0 transition-opacity duration-300 flex items-end sm:items-center justify-center p-0 sm:p-4">
        <div id="settingsModalCard" class="w-full max-w-md bg-slate-900 border border-white/20 rounded-t-3xl sm:rounded-3xl p-5 max-h-[88vh] flex flex-col transform translate-y-full transition-transform duration-300 shadow-2xl">
            <!-- Modal Header -->
            <div class="flex items-center justify-between pb-3 border-b border-white/10">
                <div class="flex items-center gap-2">
                    <span class="text-xl">⚙️</span>
                    <h3 class="text-base font-bold" id="tSettingsModalTitle">Sozlamalar</h3>
                </div>
                <button onclick="closeSettingsModal()" class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90 transition">✕</button>
            </div>

            <!-- Modal Content (Scrollable) -->
            <div class="flex-1 overflow-y-auto hide-scrollbar flex flex-col gap-3 py-3">
                <!-- Section 1: Alerts & Digest -->
                <div class="bg-white/5 border border-white/10 rounded-2xl p-3.5 flex flex-col gap-3">
                    <div class="text-xs uppercase tracking-wider font-bold text-white/70 flex items-center gap-1.5" id="tSectionAlerts">
                        <span>🔔</span> <span id="tSectionAlertsText">Bildirishnomalar</span>
                    </div>

                    <!-- Hazardous Air Alert Toggle -->
                    <div class="flex items-center justify-between pt-1">
                        <div class="pr-3">
                            <div class="text-xs font-bold text-white/90" id="lblSettingAlert">🚨 Xavfli havo xabarlari</div>
                            <div class="text-[10px] text-white/60 leading-tight mt-0.5" id="lblSettingAlertDesc">AQI zararli darajaga yetganda avtomatik ogohlantirish</div>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer flex-shrink-0">
                            <input type="checkbox" id="settingAlertToggle" onchange="onSettingToggle('alert')" class="sr-only peer">
                            <div class="w-10 h-5 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                        </label>
                    </div>

                    <div class="h-px bg-white/10 my-0.5"></div>

                    <!-- Daily Morning Digest Toggle -->
                    <div class="flex items-center justify-between">
                        <div class="pr-3">
                            <div class="text-xs font-bold text-white/90" id="lblSettingDigest">☀️ Ertalabki xabar</div>
                            <div class="text-[10px] text-white/60 leading-tight mt-0.5" id="lblSettingDigestDesc">Har tong kungi ob-havo va havo sifati ma'lumoti</div>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer flex-shrink-0">
                            <input type="checkbox" id="settingDigestToggle" onchange="onSettingToggle('digest')" class="sr-only peer">
                            <div class="w-10 h-5 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                        </label>
                    </div>
                </div>

                <!-- Section 2: Digest Schedule & Timezone -->
                <div id="settingsScheduleSection" class="bg-white/5 border border-white/10 rounded-2xl p-3.5 flex flex-col gap-3 transition">
                    <div class="text-xs uppercase tracking-wider font-bold text-white/70 flex items-center gap-1.5" id="tSectionSchedule">
                        <span>⏰</span> <span id="tSectionScheduleText">Vaqt va mintaqa</span>
                    </div>

                    <!-- Time picker pills -->
                    <div>
                        <div class="text-[11px] font-semibold text-white/80 mb-2" id="lblDigestTimeTitle">Xabar yuborish vaqti</div>
                        <div class="grid grid-cols-3 gap-1.5" id="digestTimePills">
                            <button onclick="setDigestTime('06:00')" data-time="06:00" class="time-pill py-1.5 rounded-xl text-xs font-bold bg-white/10 text-white/80 transition">06:00</button>
                            <button onclick="setDigestTime('07:00')" data-time="07:00" class="time-pill py-1.5 rounded-xl text-xs font-bold bg-sky-600 text-white transition">07:00</button>
                            <button onclick="setDigestTime('08:00')" data-time="08:00" class="time-pill py-1.5 rounded-xl text-xs font-bold bg-white/10 text-white/80 transition">08:00</button>
                            <button onclick="setDigestTime('09:00')" data-time="09:00" class="time-pill py-1.5 rounded-xl text-xs font-bold bg-white/10 text-white/80 transition">09:00</button>
                            <button onclick="setDigestTime('10:00')" data-time="10:00" class="time-pill py-1.5 rounded-xl text-xs font-bold bg-white/10 text-white/80 transition">10:00</button>
                            <button onclick="setDigestTime('11:00')" data-time="11:00" class="time-pill py-1.5 rounded-xl text-xs font-bold bg-white/10 text-white/80 transition">11:00</button>
                        </div>
                    </div>

                    <!-- Timezone Select -->
                    <div class="pt-0.5">
                        <div class="text-[11px] font-semibold text-white/80 mb-1.5" id="lblTimezoneTitle">Vaqt mintaqasi</div>
                        <select id="settingTimezoneSelect" onchange="onTimezoneChange(this.value)" class="w-full bg-slate-800 border border-white/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-400 transition">
                            <option value="auto">🌐 Avtomatik (hudud bo'yicha)</option>
                            <option value="Asia/Tashkent">🇺🇿 Toshkent (UTC+5)</option>
                            <option value="Europe/Moscow">🇷🇺 Moskva (UTC+3)</option>
                            <option value="Asia/Tokyo">🇯🇵 Tokio (UTC+9)</option>
                            <option value="Asia/Dubai">🇦🇪 Dubay (UTC+4)</option>
                            <option value="Asia/Almaty">🇰🇿 Olmaota (UTC+5)</option>
                            <option value="Europe/Istanbul">🇹🇷 Istanbul (UTC+3)</option>
                            <option value="Europe/London">🇬🇧 London (UTC+0)</option>
                            <option value="America/New_York">🇺🇸 Nyu-York (UTC-5)</option>
                            <option value="UTC">⏱ UTC (UTC+0)</option>
                        </select>
                    </div>
                </div>

                <!-- Section 3: Home District -->
                <div class="bg-white/5 border border-white/10 rounded-2xl p-3.5 flex flex-col gap-2.5">
                    <div class="text-xs uppercase tracking-wider font-bold text-white/70 flex items-center gap-1.5" id="tSectionHome">
                        <span>🏠</span> <span id="tSectionHomeText">Asosiy uy hududi</span>
                    </div>
                    <div class="text-[10px] text-white/60 leading-relaxed" id="lblHomeDesc">
                        Boshqa shahar yoki viloyatga borganingizda ham ertalabki xabarlar va ogohlantirishlar aynan uy hududingiz bo'yicha yuboriladi.
                    </div>
                    <div class="flex items-center justify-between p-2 rounded-xl bg-white/5 border border-white/10">
                        <span class="text-xs text-white/70" id="lblCurrentHomeLabel">Uy hududingiz:</span>
                        <span id="settingsHomeName" class="text-xs font-bold text-sky-300">Chilonzor</span>
                    </div>
                    <div class="flex gap-2 pt-0.5">
                        <button onclick="setHomeToCurrentDistrict()" class="flex-1 py-2 rounded-xl bg-sky-600/40 hover:bg-sky-600/60 border border-sky-400/40 text-xs font-bold text-white transition active:scale-95" id="btnSetCurrentAsHome">
                            📍 Joriy hududni uy qilish
                        </button>
                        <button onclick="clearHomeDistrict()" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-xs text-white/70 transition active:scale-95" id="btnClearHome">
                            🗑 O'chirish
                        </button>
                    </div>
                </div>

                <!-- Status Toast inside modal -->
                <div id="settingsSaveToast" class="text-center text-xs text-emerald-400 font-semibold py-0.5 opacity-0 transition-opacity duration-200">
                    ✓ Sozlamalar saqlandi
                </div>
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

        // Auto detect language from URL params or Telegram
        const urlParams = new URLSearchParams(window.location.search);
        const urlLang = urlParams.get('lang');
        const urlDistId = urlParams.get('district_id');

        if (urlDistId && !isNaN(parseInt(urlDistId))) {
            currentDistrictId = parseInt(urlDistId);
        }

        if (urlLang && ['uz', 'ru', 'en'].includes(urlLang)) {
            currentLang = urlLang;
        } else {
            const userTgLang = tg?.initDataUnsafe?.user?.language_code;
            if (userTgLang) {
                if (userTgLang.startsWith('ru')) currentLang = 'ru';
                else if (userTgLang.startsWith('en')) currentLang = 'en';
                else currentLang = 'uz';
            }
        }

        // Full UI Translation Dictionary
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
                searchPlaceholder: "Qidirish (masalan: Chilonzor, Samarqand, Istanbul)...",
                tabCity: "Toshkent tumanlari",
                tabRegions: "Viloyatlar",
                preConfiguredTitle: "Oldindan kiritilgan hududlar",
                globalResultsTitle: "Dunyo bo'ylab topilgan hududlar",
                myHomeTitle: "Mening Uyim",
                globalSearchBadge: "Global qidiruv",
                max: "Maks",
                min: "Min",
                feelsLike: "Tuyulishi",
                compass: "Kompas:",
                sunrise: "Chiqishi",
                sunset: "Botishi",
                pressureNormal: "Normal atmosfera",
                humidityComfortGood: "Qulay darajada",
                humidityComfortDry: "Quruq havo",
                humidityComfortHumid: "Yuqori namlik",
                botTitle: "Havo Bot",
                botSubtitle: "Toshkent & Viloyatlar",
                botDesc: "Real vaqt monitoringi",
                close: "Yopish ✕",
                now: "Hozir",
                today: "Bugun",
                tomorrow: "Ertaga",
                notFound: "Hudud topilmadi",
                select: "Tanlash →",
                updatedAt: "Yangilangan:",
                epaBadge: "EPA standarti",
                loading: "Yuklanmoqda...",
                analyzingAir: "Havo ma'lumotlari tahlil qilinmoqda...",
                settingsTitle: "Sozlamalar va Bildirishnomalar",
                secAlerts: "Bildirishnomalar",
                lblAlert: "🚨 Xavfli havo xabarlari",
                lblAlertDesc: "AQI zararli darajaga yetganda avtomatik ogohlantirish",
                lblDigest: "☀️ Ertalabki xabar",
                lblDigestDesc: "Har tong kungi ob-havo va havo sifati ma'lumoti",
                secSchedule: "Vaqt va mintaqa",
                lblDigestTime: "Xabar yuborish vaqti",
                lblTimezone: "Vaqt mintaqasi",
                secHome: "Asosiy uy hududi",
                lblHomeDesc: "Boshqa shahar yoki viloyatga borganingizda ham ertalabki xabarlar va ogohlantirishlar aynan uy hududingiz bo'yicha yuboriladi.",
                lblYourHome: "Uy hududingiz:",
                btnSetHome: "📍 Joriy hududni uy qilish",
                btnClearHome: "🗑 O'chirish",
                savedToast: "✓ Sozlamalar saqlandi",
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
                searchPlaceholder: "Поиск (например: Чиланзар, Самарканд, Стамбул)...",
                tabCity: "Районы Ташкента",
                tabRegions: "Области",
                preConfiguredTitle: "Стандартные регионы",
                globalResultsTitle: "Результаты глобального поиска",
                myHomeTitle: "Мой дом",
                globalSearchBadge: "Глобальный поиск",
                max: "Макс",
                min: "Мин",
                feelsLike: "Ощущается",
                compass: "Компас:",
                sunrise: "Восход",
                sunset: "Закат",
                pressureNormal: "Нормальное давление",
                humidityComfortGood: "Комфортная влажность",
                humidityComfortDry: "Сухой воздух",
                humidityComfortHumid: "Высокая влажность",
                botTitle: "Бот мониторинга",
                botSubtitle: "Ташкент и регионы",
                botDesc: "Мониторинг в реальном времени",
                close: "Закрыть ✕",
                now: "Сейчас",
                today: "Сегодня",
                tomorrow: "Завтра",
                notFound: "Район не найден",
                select: "Выбрать →",
                updatedAt: "Обновлено:",
                epaBadge: "Стандарт EPA",
                loading: "Загрузка...",
                analyzingAir: "Анализ качества воздуха...",
                settingsTitle: "Настройки и уведомления",
                secAlerts: "Уведомления",
                lblAlert: "🚨 Опасный воздух",
                lblAlertDesc: "Автоматическое оповещение при опасном AQI",
                lblDigest: "☀️ Утренний дайджест",
                lblDigestDesc: "Ежедневная утренняя сводка погоды и воздуха",
                secSchedule: "Время и часовой пояс",
                lblDigestTime: "Время отправки",
                lblTimezone: "Часовой пояс",
                secHome: "Домашний регион",
                lblHomeDesc: "Даже во время поездок уведомления и сводки будут приходить по вашему домашнему району.",
                lblYourHome: "Ваш дом:",
                btnSetHome: "📍 Сделать текущий домашним",
                btnClearHome: "🗑 Удалить",
                savedToast: "✓ Настройки сохранены",
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
                searchPlaceholder: "Search (e.g. Chilanzar, Samarkand, Istanbul)...",
                tabCity: "Tashkent Districts",
                tabRegions: "Regions",
                preConfiguredTitle: "Standard Districts",
                globalResultsTitle: "Global Search Results",
                myHomeTitle: "My Home District",
                globalSearchBadge: "Global search",
                max: "High",
                min: "Low",
                feelsLike: "Feels like",
                compass: "Compass:",
                sunrise: "Sunrise",
                sunset: "Sunset",
                pressureNormal: "Standard pressure",
                humidityComfortGood: "Comfortable",
                humidityComfortDry: "Dry air",
                humidityComfortHumid: "High humidity",
                botTitle: "Air Quality Bot",
                botSubtitle: "Tashkent & Regions",
                botDesc: "Real-time Monitoring",
                close: "Close ✕",
                now: "Now",
                today: "Today",
                tomorrow: "Tomorrow",
                notFound: "District not found",
                select: "Select →",
                updatedAt: "Updated:",
                epaBadge: "EPA standard",
                loading: "Loading...",
                analyzingAir: "Analyzing air quality...",
                settingsTitle: "Settings & Notifications",
                secAlerts: "Notifications",
                lblAlert: "🚨 Hazardous Air Alerts",
                lblAlertDesc: "Automatic alert when AQI reaches unhealthy levels",
                lblDigest: "☀️ Daily Morning Digest",
                lblDigestDesc: "Daily morning forecast and air quality summary",
                secSchedule: "Schedule & Timezone",
                lblDigestTime: "Digest Delivery Time",
                lblTimezone: "Timezone",
                secHome: "Home District",
                lblHomeDesc: "Morning digests and hazardous air alerts are always delivered for your home district, even when traveling.",
                lblYourHome: "Home district:",
                btnSetHome: "📍 Set current as Home",
                btnClearHome: "🗑 Clear",
                savedToast: "✓ Settings saved",
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

            document.getElementById('lblUpdatedAt').textContent = t.updatedAt;
            document.getElementById('lblCompass').textContent = t.compass;
            document.getElementById('lblSunrise').textContent = t.sunrise;
            document.getElementById('lblSunset').textContent = t.sunset;
            document.getElementById('lblPressureDesc').textContent = t.pressureNormal;
            document.getElementById('botTitle').textContent = t.botTitle;
            document.getElementById('botSubtitle').textContent = t.botSubtitle;
            document.getElementById('botDesc').textContent = t.botDesc;
            document.getElementById('btnClose').textContent = t.close;
            document.getElementById('badgePm25').textContent = t.epaBadge;
            document.getElementById('badgePm10').textContent = t.epaBadge;

            // Dynamic placeholders if not loaded yet
            const weatherCondEl = document.getElementById('weatherCondition');
            if (weatherCondEl && (weatherCondEl.textContent.includes('...') || ['Yuklanmoqda...', 'Загрузка...', 'Loading...'].includes(weatherCondEl.textContent))) {
                weatherCondEl.textContent = t.loading;
            }
            const aqiAdviceEl = document.getElementById('aqiAdviceText');
            if (aqiAdviceEl && (aqiAdviceEl.textContent.includes('...') || aqiAdviceEl.textContent.includes('tahlil') || aqiAdviceEl.textContent.includes('Анализ') || aqiAdviceEl.textContent.includes('Analyzing'))) {
                aqiAdviceEl.textContent = t.analyzingAir;
            }
            const tempRangeEl = document.getElementById('tempRange');
            if (tempRangeEl && tempRangeEl.textContent.includes('--')) {
                tempRangeEl.textContent = `${t.max}: --° • ${t.min}: --°`;
            }
            const feelsLikeEl = document.getElementById('feelsLike');
            if (feelsLikeEl && feelsLikeEl.textContent.includes('--')) {
                feelsLikeEl.textContent = `${t.feelsLike}: --°`;
            }

            // Active lang dropdown button & checkmark update
            const flags = { uz: '🇺🇿', ru: '🇷🇺', en: '🇬🇧' };
            const labels = { uz: 'UZ', ru: 'RU', en: 'EN' };
            const flagEl = document.getElementById('currentLangFlag');
            const labelEl = document.getElementById('currentLangLabel');
            if (flagEl) flagEl.textContent = flags[currentLang] || '🇺🇿';
            if (labelEl) labelEl.textContent = labels[currentLang] || 'UZ';

            ['uz', 'ru', 'en'].forEach(l => {
                const checkEl = document.getElementById('check' + l.charAt(0).toUpperCase() + l.slice(1));
                if (checkEl) {
                    if (l === currentLang) checkEl.classList.remove('hidden');
                    else checkEl.classList.add('hidden');
                }
            });

            // Settings Modal texts
            const sTitle = document.getElementById('tSettingsModalTitle');
            if (sTitle) sTitle.textContent = t.settingsTitle;
            const secAlertsEl = document.getElementById('tSectionAlertsText');
            if (secAlertsEl) secAlertsEl.textContent = t.secAlerts;
            const lblAlertEl = document.getElementById('lblSettingAlert');
            if (lblAlertEl) lblAlertEl.textContent = t.lblAlert;
            const lblAlertDescEl = document.getElementById('lblSettingAlertDesc');
            if (lblAlertDescEl) lblAlertDescEl.textContent = t.lblAlertDesc;
            const lblDigestEl = document.getElementById('lblSettingDigest');
            if (lblDigestEl) lblDigestEl.textContent = t.lblDigest;
            const lblDigestDescEl = document.getElementById('lblSettingDigestDesc');
            if (lblDigestDescEl) lblDigestDescEl.textContent = t.lblDigestDesc;
            const secSchedEl = document.getElementById('tSectionScheduleText');
            if (secSchedEl) secSchedEl.textContent = t.secSchedule;
            const lblDigestTimeEl = document.getElementById('lblDigestTimeTitle');
            if (lblDigestTimeEl) lblDigestTimeEl.textContent = t.lblDigestTime;
            const lblTimezoneEl = document.getElementById('lblTimezoneTitle');
            if (lblTimezoneEl) lblTimezoneEl.textContent = t.lblTimezone;
            const secHomeEl = document.getElementById('tSectionHomeText');
            if (secHomeEl) secHomeEl.textContent = t.secHome;
            const lblHomeDescEl = document.getElementById('lblHomeDesc');
            if (lblHomeDescEl) lblHomeDescEl.textContent = t.lblHomeDesc;
            const lblCurHomeEl = document.getElementById('lblCurrentHomeLabel');
            if (lblCurHomeEl) lblCurHomeEl.textContent = t.lblYourHome;
            const btnSetHomeEl = document.getElementById('btnSetCurrentAsHome');
            if (btnSetHomeEl) btnSetHomeEl.textContent = t.btnSetHome;
            const btnClearHomeEl = document.getElementById('btnClearHome');
            if (btnClearHomeEl) btnClearHomeEl.textContent = t.btnClearHome;
            const sToast = document.getElementById('settingsSaveToast');
            if (sToast) sToast.textContent = t.savedToast;

            // District Modal texts
            const hdBanner = document.getElementById('lblHomeDistrictBanner');
            if (hdBanner) hdBanner.textContent = t.myHomeTitle;
            const hdSelBtn = document.getElementById('lblSelectHomeBtn');
            if (hdSelBtn) hdSelBtn.textContent = t.select.replace(' →', '');
            const gSearchBadge = document.getElementById('lblGlobalSearchBadge');
            if (gSearchBadge) gSearchBadge.textContent = t.globalSearchBadge;
            const searchResTitle = document.getElementById('lblSearchResultsTitle');
            if (searchResTitle) searchResTitle.textContent = t.preConfiguredTitle;
        }

        // --- Settings Management ---
        let userSettings = {
            alert_enabled: true,
            daily_digest: false,
            digest_time: "07:00",
            timezone: "auto",
            home_district_id: null,
            home_district_name: "—"
        };

        async function loadUserSettings() {
            const tgUser = tg?.initDataUnsafe?.user;
            const tgId = tgUser?.id;
            if (!tgId) {
                try {
                    const local = localStorage.getItem('havo_user_settings');
                    if (local) {
                        userSettings = Object.assign(userSettings, JSON.parse(local));
                    }
                } catch(e) {}
                renderSettingsUI();
                return;
            }

            try {
                const res = await fetch(`/api/miniapp/settings?telegram_id=${tgId}&lang=${currentLang}`);
                if (res.ok) {
                    userSettings = await res.json();
                    renderSettingsUI();
                }
            } catch(e) {
                console.error("Sozlamalarni yuklashda xatolik:", e);
            }
        }

        function renderSettingsUI() {
            const alertToggle = document.getElementById('settingAlertToggle');
            const digestToggle = document.getElementById('settingDigestToggle');
            const homeNameEl = document.getElementById('settingsHomeName');
            const tzSelect = document.getElementById('settingTimezoneSelect');

            if (alertToggle) alertToggle.checked = !!userSettings.alert_enabled;
            if (digestToggle) digestToggle.checked = !!userSettings.daily_digest;
            if (homeNameEl) homeNameEl.textContent = userSettings.home_district_name || '—';
            if (tzSelect) tzSelect.value = userSettings.timezone || 'auto';

            document.querySelectorAll('.time-pill').forEach(btn => {
                const tm = btn.getAttribute('data-time');
                if (tm === userSettings.digest_time) {
                    btn.className = "time-pill py-1.5 rounded-xl text-xs font-bold bg-sky-600 text-white shadow-md transition";
                } else {
                    btn.className = "time-pill py-1.5 rounded-xl text-xs font-bold bg-white/10 text-white/80 hover:bg-white/20 transition";
                }
            });

            const schedSec = document.getElementById('settingsScheduleSection');
            if (schedSec) {
                if (userSettings.daily_digest) {
                    schedSec.classList.remove('opacity-40', 'pointer-events-none');
                } else {
                    schedSec.classList.add('opacity-40', 'pointer-events-none');
                }
            }
        }

        async function saveSettings(partialUpdate) {
            haptic('selection');
            userSettings = Object.assign(userSettings, partialUpdate);
            renderSettingsUI();

            const tgUser = tg?.initDataUnsafe?.user;
            const tgId = tgUser?.id;

            try {
                localStorage.setItem('havo_user_settings', JSON.stringify(userSettings));
            } catch(e) {}

            if (tgId) {
                try {
                    const payload = Object.assign({ telegram_id: tgId }, partialUpdate);
                    const res = await fetch(`/api/miniapp/settings?lang=${currentLang}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data.settings) {
                            userSettings = data.settings;
                            renderSettingsUI();
                        }
                    }
                } catch(e) {
                    console.error("Sozlamalarni saqlashda xatolik:", e);
                }
            }

            const toast = document.getElementById('settingsSaveToast');
            if (toast) {
                toast.classList.remove('opacity-0');
                setTimeout(() => toast.classList.add('opacity-0'), 1500);
            }
        }

        function onSettingToggle(type) {
            if (type === 'alert') {
                const val = document.getElementById('settingAlertToggle').checked;
                saveSettings({ alert_enabled: val });
            } else if (type === 'digest') {
                const val = document.getElementById('settingDigestToggle').checked;
                saveSettings({ daily_digest: val });
            }
        }

        function setDigestTime(timeStr) {
            saveSettings({ digest_time: timeStr });
        }

        function onTimezoneChange(tzVal) {
            saveSettings({ timezone: tzVal });
        }

        function setHomeToCurrentDistrict() {
            const curDistName = document.getElementById('currentDistrictName')?.textContent || '—';
            saveSettings({ home_district_id: currentDistrictId, home_district_name: curDistName });
        }

        function clearHomeDistrict() {
            saveSettings({ clear_home: true, home_district_id: null, home_district_name: '—' });
        }

        function openSettingsModal() {
            haptic('light');
            loadUserSettings();
            const modal = document.getElementById('settingsModal');
            const card = document.getElementById('settingsModalCard');
            modal.classList.remove('hidden');
            setTimeout(() => {
                modal.classList.remove('opacity-0');
                card.classList.remove('translate-y-full');
            }, 10);
        }

        function closeSettingsModal() {
            haptic('light');
            const modal = document.getElementById('settingsModal');
            const card = document.getElementById('settingsModalCard');
            modal.classList.add('opacity-0');
            card.classList.add('translate-y-full');
            setTimeout(() => {
                modal.classList.add('hidden');
            }, 300);
        }

        function toggleLangMenu(event) {
            if (event) event.stopPropagation();
            haptic('light');
            const menu = document.getElementById('langDropdownMenu');
            const chevron = document.getElementById('langChevron');
            const isHidden = menu.classList.contains('hidden');
            if (isHidden) {
                menu.classList.remove('hidden');
                chevron.classList.add('rotate-180');
            } else {
                menu.classList.add('hidden');
                chevron.classList.remove('rotate-180');
            }
        }

        function closeLangMenu() {
            const menu = document.getElementById('langDropdownMenu');
            const chevron = document.getElementById('langChevron');
            if (menu && !menu.classList.contains('hidden')) {
                menu.classList.add('hidden');
                chevron?.classList.remove('rotate-180');
            }
        }

        function selectLang(lang) {
            closeLangMenu();
            if (currentLang === lang) return;
            changeLang(lang);
        }

        document.addEventListener('click', (e) => {
            const container = document.getElementById('langMenuContainer');
            if (container && !container.contains(e.target)) {
                closeLangMenu();
            }
        });

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
            const t = I18N[currentLang] || I18N.uz;

            // 1. District
            document.getElementById('currentDistrictName').textContent = district.name;

            // 2. Weather Hero
            document.getElementById('weatherEmojiHero').textContent = weather.emoji || '☀️';
            document.getElementById('weatherTemp').innerHTML = `<span>${Math.round(weather.temp)}</span><span class="text-4xl font-normal mt-1 text-white/80">°</span>`;
            document.getElementById('weatherCondition').textContent = weather.condition;
            document.getElementById('tempRange').textContent = `${t.max}: ${Math.round(weather.temp_max)}° • ${t.min}: ${Math.round(weather.temp_min)}°`;
            document.getElementById('feelsLike').textContent = `${t.feelsLike}: ${Math.round(weather.feels_like)}°`;

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
            document.getElementById('aqiUpdatedTime').textContent = air.updated_at || '--:--';
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

            // 4. Hourly Forecast (Today vs Tomorrow clear differentiation)
            const hourlyEl = document.getElementById('hourlyContainer');
            if (hourly && hourly.length > 0) {
                let seenTomorrow = false;
                let prevHour = -1;

                hourlyEl.innerHTML = hourly.map(item => {
                    const hourNum = parseInt(item.time.split(':')[0], 10);
                    if (item.is_tomorrow || (prevHour !== -1 && hourNum < prevHour)) {
                        seenTomorrow = true;
                    }
                    prevHour = hourNum;
                    const isTomorrow = item.is_tomorrow || seenTomorrow;

                    let dayBadge = t.today;
                    let badgeClass = 'text-white/45 font-semibold';
                    let cardBg = 'bg-white/5 border border-white/5';

                    if (item.is_now) {
                        dayBadge = '●';
                        badgeClass = 'text-sky-300 font-black';
                        cardBg = 'bg-white/25 border border-white/35 shadow-md';
                    } else if (isTomorrow) {
                        dayBadge = t.tomorrow;
                        badgeClass = 'text-amber-300 font-bold';
                        cardBg = 'bg-white/5 border border-amber-300/30 shadow-sm shadow-amber-500/5';
                    }

                    return `
                    <div class="flex-shrink-0 w-[68px] py-2.5 px-1.5 rounded-2xl flex flex-col items-center justify-between text-center transition ${cardBg}">
                        <div class="flex flex-col items-center w-full leading-tight">
                            <span class="text-[9px] ${badgeClass} uppercase tracking-tight truncate w-full">${dayBadge}</span>
                            <span class="text-[11px] font-bold ${item.is_now ? 'text-white' : 'text-white/85'} mt-0.5">${item.is_now ? t.now : item.time}</span>
                        </div>
                        <span class="text-2xl my-1.5 filter drop-shadow">${item.emoji}</span>
                        <span class="text-sm font-bold font-sans">${Math.round(item.temp)}°</span>
                        ${item.pop > 10 ? `<span class="text-[9px] font-bold text-sky-300 mt-0.5">💧${item.pop}%</span>` : ''}
                    </div>
                    `;
                }).join('');
            }

            // 5. Weekly Forecast (Dynamic for ANY temperature range including winter/subzero)
            const weeklyEl = document.getElementById('weeklyContainer');
            if (weekly && weekly.length > 0) {
                const allMin = Math.min(...weekly.map(d => d.temp_min));
                const allMax = Math.max(...weekly.map(d => d.temp_max));
                const range = Math.max(1, allMax - allMin);

                weeklyEl.innerHTML = weekly.map((day, idx) => {
                    let leftPct = Math.round(((day.temp_min - allMin) / range) * 100);
                    let widthPct = Math.round(((day.temp_max - day.temp_min) / range) * 100);

                    // Elegant minimum bar width (16%) so narrow ranges (e.g. 12°-13°) look clean and rounded
                    widthPct = Math.max(16, widthPct);
                    if (leftPct + widthPct > 100) {
                        leftPct = Math.max(0, 100 - widthPct);
                    }

                    // Live current temp dot on "Today" row (Apple Weather signature feature)
                    let dotHtml = '';
                    if (idx === 0) {
                        const cur = Math.round(weather.temp);
                        const clamped = Math.min(day.temp_max, Math.max(day.temp_min, cur));
                        const dotPct = day.temp_max === day.temp_min ? 50 : Math.round(((clamped - day.temp_min) / Math.max(0.1, day.temp_max - day.temp_min)) * 100);
                        dotHtml = `<div class="absolute -top-1 w-3 h-3 bg-white rounded-full border-2 border-slate-900 shadow-sm z-10 pointer-events-none" style="left: calc(${dotPct}% - 6px);"></div>`;
                    }

                    const isToday = idx === 0;
                    const dayLabel = isToday ? t.today : (idx === 1 ? t.tomorrow : day.day_name);

                    return `
                    <div class="py-2.5 flex items-center justify-between text-xs font-medium">
                        <span class="w-16 font-semibold truncate ${isToday ? 'text-sky-300 font-bold' : 'text-white'}">${dayLabel}</span>
                        <div class="w-8 text-center text-lg">${day.emoji}</div>
                        <span class="w-10 text-right font-mono text-white/70 font-bold">${Math.round(day.temp_min)}°</span>
                        <div class="flex-1 mx-3 h-1.5 bg-white/10 rounded-full relative overflow-visible">
                            <div class="absolute h-full rounded-full bg-gradient-to-r from-sky-400 via-amber-300 to-orange-400" style="left: ${leftPct}%; width: ${widthPct}%;">
                                ${dotHtml}
                            </div>
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

            let humidDesc = t.humidityComfortGood;
            if (weather.humidity < 30) humidDesc = t.humidityComfortDry;
            else if (weather.humidity > 65) humidDesc = t.humidityComfortHumid;
            document.getElementById('valHumidityComfort').textContent = humidDesc;

            document.getElementById('valUv').textContent = weather.uv_index;
            document.getElementById('valUvDesc').textContent = weather.uv_category;

            document.getElementById('valSunrise').textContent = weather.sunrise;
            document.getElementById('valSunset').textContent = weather.sunset;
            document.getElementById('sunPosDot').style.left = `${Math.min(95, Math.max(5, weather.sun_progress * 100))}%`;

            document.getElementById('valPressureMmhg').textContent = weather.pressure_mmhg;
            document.getElementById('valPressureHpa').textContent = `${weather.pressure_hpa} hPa`;
        }

        async function loadDistrictsList() {
            const tgUser = tg?.initDataUnsafe?.user;
            const tgId = tgUser?.id || '';
            try {
                const res = await fetch(`/api/miniapp/districts?lang=${currentLang}&telegram_id=${tgId}`);
                allDistricts = await res.json();
                updateHomeDistrictBanner();
                renderDistrictsList();
                updateStaticTexts();
            } catch(e) {
                console.error("Hududlar ro'yxatini yuklashda xatolik:", e);
            }
        }

        let searchDebounceTimer = null;
        let globalSearchResults = [];

        function handleDistrictSearch(val) {
            clearTimeout(searchDebounceTimer);
            const query = (val || '').trim();

            if (!query) {
                document.getElementById('districtTabsContainer')?.classList.remove('hidden');
                document.getElementById('searchSectionHeader')?.classList.add('hidden');
                document.getElementById('searchSpinner')?.classList.add('hidden');
                updateHomeDistrictBanner();
                renderDistrictsList();
                return;
            }

            document.getElementById('districtTabsContainer')?.classList.add('hidden');
            document.getElementById('homeDistrictQuickCard')?.classList.add('hidden');
            document.getElementById('searchSectionHeader')?.classList.remove('hidden');

            renderLocalMatchingDistricts(query);

            const spinner = document.getElementById('searchSpinner');
            if (spinner) spinner.classList.remove('hidden');

            searchDebounceTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/miniapp/search?q=${encodeURIComponent(query)}&lang=${currentLang}`);
                    if (res.ok) {
                        globalSearchResults = await res.json();
                    } else {
                        globalSearchResults = [];
                    }
                } catch (e) {
                    globalSearchResults = [];
                } finally {
                    if (spinner) spinner.classList.add('hidden');
                    renderSearchResults(query);
                }
            }, 350);
        }

        function renderLocalMatchingDistricts(query) {
            const t = I18N[currentLang] || I18N.uz;
            const container = document.getElementById('districtListScroll');
            const q = query.toLowerCase();

            const allLocal = [...(allDistricts.city || []), ...(allDistricts.regions || [])];
            const localMatches = allLocal.filter(d => d.name.toLowerCase().includes(q));

            let html = '';
            if (localMatches.length > 0) {
                html += `<div class="text-[10px] font-bold text-sky-400 uppercase tracking-wider px-1 pt-1 pb-0.5">${t.preConfiguredTitle}</div>`;
                html += localMatches.map(d => `
                    <button onclick="selectDistrict(${d.id})" class="w-full text-left p-3 rounded-xl flex items-center justify-between transition ${d.id === currentDistrictId ? 'bg-sky-600/40 border border-sky-400/50 font-bold' : 'bg-white/5 hover:bg-white/10 text-white/80'}">
                        <span class="flex items-center gap-2"><span>📍</span> <span>${d.name}</span></span>
                        ${d.id === currentDistrictId ? '<span class="text-sky-300">✓</span>' : `<span class="text-white/30 text-xs">${t.select}</span>`}
                    </button>
                `).join('');
            }
            container.innerHTML = html;
        }

        function renderSearchResults(query) {
            const t = I18N[currentLang] || I18N.uz;
            const container = document.getElementById('districtListScroll');
            const q = query.toLowerCase();

            const allLocal = [...(allDistricts.city || []), ...(allDistricts.regions || [])];
            const localMatches = allLocal.filter(d => d.name.toLowerCase().includes(q));

            let html = '';

            // 1. Local pre-configured matches
            if (localMatches.length > 0) {
                html += `<div class="text-[10px] font-bold text-sky-400 uppercase tracking-wider px-1 pt-1 pb-0.5">${t.preConfiguredTitle}</div>`;
                html += localMatches.map(d => `
                    <button onclick="selectDistrict(${d.id})" class="w-full text-left p-3 rounded-xl flex items-center justify-between transition ${d.id === currentDistrictId ? 'bg-sky-600/40 border border-sky-400/50 font-bold' : 'bg-white/5 hover:bg-white/10 text-white/80'}">
                        <span class="flex items-center gap-2"><span>📍</span> <span>${d.name}</span></span>
                        ${d.id === currentDistrictId ? '<span class="text-sky-300">✓</span>' : `<span class="text-white/30 text-xs">${t.select}</span>`}
                    </button>
                `).join('');
            }

            // 2. Global search results
            if (globalSearchResults.length > 0) {
                html += `<div class="text-[10px] font-bold text-amber-300 uppercase tracking-wider px-1 pt-2 pb-0.5 flex items-center gap-1.5"><span>🌍</span> <span>${t.globalResultsTitle}</span></div>`;
                html += globalSearchResults.map((loc, idx) => `
                    <button onclick="selectGlobalLocation(${idx})" class="w-full text-left p-3 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-sky-400/30 transition flex items-center justify-between">
                        <div class="flex items-center gap-2.5 truncate pr-2">
                            <span class="text-base flex-shrink-0">🌐</span>
                            <div class="truncate">
                                <div class="text-xs font-bold text-white truncate">${loc.name}</div>
                                <div class="text-[10px] text-white/50 truncate">${loc.country || ''} ${loc.admin_area ? '• ' + loc.admin_area : ''}</div>
                            </div>
                        </div>
                        <span class="text-xs text-sky-300 font-semibold flex-shrink-0">${t.select}</span>
                    </button>
                `).join('');
            }

            if (localMatches.length === 0 && globalSearchResults.length === 0) {
                html = `<div class="text-center py-8 text-white/40 text-xs">${t.notFound}</div>`;
            }

            container.innerHTML = html;
        }

        async function selectGlobalLocation(index) {
            haptic('medium');
            const loc = globalSearchResults[index];
            if (!loc) return;

            const tgUser = tg?.initDataUnsafe?.user;
            const tgId = tgUser?.id;

            try {
                const res = await fetch(`/api/miniapp/select-location?lang=${currentLang}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(Object.assign({ telegram_id: tgId }, loc))
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.district) {
                        currentDistrictId = data.district.id;
                        closeDistrictModal();
                        loadData();
                        return;
                    }
                }
            } catch (e) {
                console.error("Global hududni tanlashda xatolik:", e);
            }

            closeDistrictModal();
            loadData();
        }

        function selectHomeDistrict() {
            if (allDistricts.home && allDistricts.home.id) {
                selectDistrict(allDistricts.home.id);
            }
        }

        function updateHomeDistrictBanner() {
            const homeCard = document.getElementById('homeDistrictQuickCard');
            const homeName = document.getElementById('homeDistrictBannerName');
            const searchVal = document.getElementById('districtSearchInput')?.value?.trim();

            if (!searchVal && allDistricts.home && allDistricts.home.id) {
                if (homeName) homeName.textContent = allDistricts.home.name;
                homeCard?.classList.remove('hidden');
            } else {
                homeCard?.classList.add('hidden');
            }
        }

        function renderDistrictsList() {
            const t = I18N[currentLang] || I18N.uz;
            const list = allDistricts[currentTab] || [];
            const container = document.getElementById('districtListScroll');

            if (list.length === 0) {
                container.innerHTML = `<div class="text-center py-6 text-white/40 text-xs">${t.notFound}</div>`;
                return;
            }

            container.innerHTML = list.map(d => `
                <button onclick="selectDistrict(${d.id})" class="w-full text-left p-3 rounded-xl flex items-center justify-between transition ${d.id === currentDistrictId ? 'bg-sky-600/40 border border-sky-400/50 font-bold' : 'bg-white/5 hover:bg-white/10 text-white/80'}">
                    <span>${d.name}</span>
                    ${d.id === currentDistrictId ? '<span class="text-sky-300">✓</span>' : `<span class="text-white/30 text-xs">${t.select}</span>`}
                </button>
            `).join('');
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
            const searchInput = document.getElementById('districtSearchInput');
            if (searchInput) searchInput.value = '';
            document.getElementById('districtTabsContainer')?.classList.remove('hidden');
            document.getElementById('searchSectionHeader')?.classList.add('hidden');
            document.getElementById('searchSpinner')?.classList.add('hidden');
            updateHomeDistrictBanner();
            renderDistrictsList();

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
            loadUserSettings();
            loadData();
        }

        function refreshData() {
            haptic('medium');
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('spin-anim');
            setTimeout(() => btn.classList.remove('spin-anim'), 650);
            loadData();
            loadUserSettings();
        }

        function closeMiniApp() {
            if (tg) {
                tg.close();
            } else {
                window.history.back();
            }
        }

        // Close modals on outside backdrop click
        document.getElementById('districtModal')?.addEventListener('click', (e) => {
            if (e.target.id === 'districtModal') closeDistrictModal();
        });
        document.getElementById('settingsModal')?.addEventListener('click', (e) => {
            if (e.target.id === 'settingsModal') closeSettingsModal();
        });

        // Initialize on load
        window.addEventListener('DOMContentLoaded', () => {
            updateStaticTexts();
            loadDistrictsList();
            loadUserSettings();
            loadData();
        });
    </script>
</body>
</html>
"""
