"""Telegram Mini App API va HTML routeri."""

from collections import defaultdict
import html
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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


@miniapp_router.get("/favicon.ico")
async def favicon() -> Response:
    """Brauzerlar uchun favicon 404 logini oldini olish."""
    return Response(status_code=204)


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
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🌤</text></svg>">
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
                <span class="w-4 h-4 text-rose-400 flex items-center justify-center flex-shrink-0">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 21c-4-4.5-7-8.5-7-12a7 7 0 0 1 14 0c0 3.5-3 7.5-7 12z"/><circle cx="12" cy="9" r="2.5" fill="currentColor"/></svg>
                </span>
                <span id="currentDistrictName">Yuklanmoqda...</span>
                <svg class="w-4 h-4 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
            </button>

            <!-- Actions: Lang Switcher, Refresh & Settings -->
            <div class="flex items-center gap-2">
                <!-- Language Selector Dropdown -->
                <div class="relative" id="langMenuContainer">
                    <button onclick="toggleLangMenu(event)" id="langDropdownBtn" class="glass-pill px-3 py-1.5 rounded-full flex items-center gap-1.5 text-xs font-bold active:scale-95 transition shadow-sm">
                        <span class="w-3.5 h-3.5 text-sky-300 flex items-center justify-center flex-shrink-0">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a14.5 14.5 0 0 1 0 18a14.5 14.5 0 0 1 0-18z"/></svg>
                        </span>
                        <span id="currentLangLabel">UZ</span>
                        <svg class="w-3 h-3 opacity-70 transform transition-transform duration-200" id="langChevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>

                    <!-- Language Popup Dropdown -->
                    <div id="langDropdownMenu" class="absolute right-0 mt-1.5 w-36 bg-slate-900/95 border border-white/20 p-1.5 rounded-2xl hidden z-50 shadow-2xl backdrop-blur-2xl flex flex-col gap-0.5">
                        <button onclick="selectLang('uz')" class="flex items-center justify-between w-full px-2.5 py-1.5 rounded-xl text-xs font-semibold hover:bg-white/15 transition text-left">
                            <span class="flex items-center gap-2 font-bold text-white"><span class="text-sky-300 font-mono text-[10px] px-1 py-0.5 bg-white/10 rounded">UZ</span> <span>O'zbekcha</span></span>
                            <span id="checkUz" class="text-sky-300 font-bold">✓</span>
                        </button>
                        <button onclick="selectLang('ru')" class="flex items-center justify-between w-full px-2.5 py-1.5 rounded-xl text-xs font-semibold hover:bg-white/15 transition text-left">
                            <span class="flex items-center gap-2 font-bold text-white"><span class="text-sky-300 font-mono text-[10px] px-1 py-0.5 bg-white/10 rounded">RU</span> <span>Русский</span></span>
                            <span id="checkRu" class="text-sky-300 font-bold hidden">✓</span>
                        </button>
                        <button onclick="selectLang('en')" class="flex items-center justify-between w-full px-2.5 py-1.5 rounded-xl text-xs font-semibold hover:bg-white/15 transition text-left">
                            <span class="flex items-center gap-2 font-bold text-white"><span class="text-sky-300 font-mono text-[10px] px-1 py-0.5 bg-white/10 rounded">EN</span> <span>English</span></span>
                            <span id="checkEn" class="text-sky-300 font-bold hidden">✓</span>
                        </button>
                    </div>
                </div>

                <!-- Refresh Button -->
                <button onclick="refreshData()" id="refreshBtn" class="glass-pill w-8 h-8 rounded-full flex items-center justify-center active:scale-90 transition" title="Yangilash">
                    <svg class="w-4 h-4 text-white/90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
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
            <div id="weatherIconHero" class="w-24 h-24 mb-1 select-none transform hover:scale-105 transition-transform duration-300 flex items-center justify-center">
                <!-- Dynamically populated 3D Weather Icon -->
            </div>
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
                    <span class="w-4 h-4 text-emerald-400 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" class="w-full h-full"><path d="M4 20 C6 14 11 9 19 5 C19 13 14 18 8 20 Z" fill="#10B981" stroke="#34D399" stroke-width="1.5"/><path d="M7 17 C10 13 13 10 17 7" stroke="#FFFFFF" stroke-width="1.3" stroke-linecap="round" opacity="0.8"/></svg>
                    </span>
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
                        <div id="aqiGaugeCenterIcon" class="w-7 h-7 flex items-center justify-center">
                            <!-- Dynamically colored AQI icon -->
                        </div>
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
                <span class="w-4 h-4 text-sky-300 flex items-center justify-center flex-shrink-0">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>
                </span>
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
                <span class="w-4 h-4 text-sky-300 flex items-center justify-center flex-shrink-0">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="3" y="4" width="18" height="17" rx="3"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><circle cx="8" cy="14" r="1" fill="currentColor"/><circle cx="12" cy="14" r="1" fill="currentColor"/><circle cx="16" cy="14" r="1" fill="currentColor"/></svg>
                </span>
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
                    <span class="w-4 h-4 text-sky-300 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M4 8h10.5a2.5 2.5 0 1 0-2.5-2.5"/><path d="M2 13h15.5a3 3 0 1 0-3-3"/><path d="M7 18h7a2 2 0 1 0-2-2"/></svg>
                    </span>
                    <span id="tWindTitle">Shamol</span>
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
                    <span class="w-4 h-4 text-cyan-300 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" class="w-full h-full"><path d="M12 2.5 C12 2.5 5 11 5 16 A 7 7 0 0 0 19 16 C19 11 12 2.5 12 2.5 Z" fill="#0284C7" stroke="#38BDF8" stroke-width="1.6"/><path d="M9 14.5 A 3.5 3.5 0 0 0 12 18" stroke="#FFFFFF" stroke-width="1.4" stroke-linecap="round" opacity="0.8"/></svg>
                    </span>
                    <span id="tHumidityTitle">Namlik</span>
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
                    <span class="w-4 h-4 text-amber-300 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
                    </span>
                    <span id="tUvTitle">UV Indeksi</span>
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
                    <span class="w-4 h-4 text-amber-400 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 18h18"/><path d="M7 18a5 5 0 0 1 10 0"/><path d="M12 7V4M17 9l2-2M7 9L5 7"/></svg>
                    </span>
                    <span id="tSunTitle">Quyosh</span>
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
                    <span class="w-4 h-4 text-violet-300 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 1.5"/><path d="M9 3h6"/></svg>
                    </span>
                    <span id="tPressureTitle">Bosim</span>
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
                    <span class="w-4 h-4 text-sky-300 flex items-center justify-center flex-shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="5" y="4" width="14" height="16" rx="3"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/><path d="M9 14h6"/><path d="M12 1v3"/></svg>
                    </span>
                    <span id="botTitle">Havo Bot</span>
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
                    <span class="w-5 h-5 text-sky-400 flex items-center justify-center">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 21h18M5 21V7l8-4v18M13 10l6 3v8M9 9v.01M9 13v.01M9 17v.01M17 15v.01M17 18v.01"/></svg>
                    </span>
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
                        <span class="w-5 h-5 text-amber-300 flex items-center justify-center flex-shrink-0">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 10.5L12 3l9 7.5V20a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9.5z"/><path d="M9 22V12h6v10"/></svg>
                        </span>
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
                    <span class="w-5 h-5 text-sky-400 flex items-center justify-center">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                    </span>
                    <h3 class="text-base font-bold" id="tSettingsModalTitle">Sozlamalar</h3>
                </div>
                <button onclick="closeSettingsModal()" class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90 transition">✕</button>
            </div>

            <!-- Modal Content (Scrollable) -->
            <div class="flex-1 overflow-y-auto hide-scrollbar flex flex-col gap-3 py-3">
                <!-- Section 1: Alerts & Digest -->
                <div class="bg-white/5 border border-white/10 rounded-2xl p-3.5 flex flex-col gap-3">
                    <div class="text-xs uppercase tracking-wider font-bold text-white/70 flex items-center gap-1.5" id="tSectionAlerts">
                        <span class="w-4 h-4 text-sky-300 flex items-center justify-center">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
                        </span>
                        <span id="tSectionAlertsText">Bildirishnomalar</span>
                    </div>

                    <!-- Hazardous Air Alert Toggle -->
                    <div class="flex items-center justify-between pt-1">
                        <div class="pr-3">
                            <div class="text-xs font-bold text-white/90 flex items-center gap-1.5">
                                <span class="w-3.5 h-3.5 text-amber-400 flex items-center justify-center flex-shrink-0">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                                </span>
                                <span id="lblSettingAlert">Xavfli havo xabarlari</span>
                            </div>
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
                            <div class="text-xs font-bold text-white/90 flex items-center gap-1.5">
                                <span class="w-3.5 h-3.5 text-amber-300 flex items-center justify-center flex-shrink-0">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
                                </span>
                                <span id="lblSettingDigest">Ertalabki xabar</span>
                            </div>
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
                        <span class="w-4 h-4 text-sky-300 flex items-center justify-center">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>
                        </span>
                        <span id="tSectionScheduleText">Vaqt va mintaqa</span>
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
                        <span class="w-4 h-4 text-amber-300 flex items-center justify-center">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 10.5L12 3l9 7.5V20a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9.5z"/><path d="M9 22V12h6v10"/></svg>
                        </span>
                        <span id="tSectionHomeText">Asosiy uy hududi</span>
                    </div>
                    <div class="text-[10px] text-white/60 leading-relaxed" id="lblHomeDesc">
                        Boshqa shahar yoki viloyatga borganingizda ham ertalabki xabarlar va ogohlantirishlar aynan uy hududingiz bo'yicha yuboriladi.
                    </div>
                    <div class="flex items-center justify-between p-2 rounded-xl bg-white/5 border border-white/10">
                        <span class="text-xs text-white/70" id="lblCurrentHomeLabel">Uy hududingiz:</span>
                        <span id="settingsHomeName" class="text-xs font-bold text-sky-300">Chilonzor</span>
                    </div>
                    <div class="flex gap-2 pt-0.5">
                        <button onclick="setHomeToCurrentDistrict()" class="flex-1 py-2 rounded-xl bg-sky-600/40 hover:bg-sky-600/60 border border-sky-400/40 text-xs font-bold text-white transition active:scale-95 flex items-center justify-center gap-1.5" id="btnSetCurrentAsHome">
                            <span class="w-3.5 h-3.5 text-rose-400 flex items-center justify-center flex-shrink-0">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 21c-4-4.5-7-8.5-7-12a7 7 0 0 1 14 0c0 3.5-3 7.5-7 12z"/><circle cx="12" cy="9" r="2.5" fill="currentColor"/></svg>
                            </span>
                            <span id="btnSetCurrentAsHomeText">Joriy hududni uy qilish</span>
                        </button>
                        <button onclick="clearHomeDistrict()" class="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-xs text-white/70 transition active:scale-95 flex items-center justify-center gap-1.5" id="btnClearHome">
                            <span class="w-3.5 h-3.5 text-rose-400 flex items-center justify-center flex-shrink-0">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            </span>
                            <span id="btnClearHomeText">O'chirish</span>
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

        // High-Precision SVG System (Apple Weather & SF Symbols inspired)
        const AppIcons = {
            wind: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M4 8h10.5a2.5 2.5 0 1 0-2.5-2.5"/><path d="M2 13h15.5a3 3 0 1 0-3-3"/><path d="M7 18h7a2 2 0 1 0-2-2"/></svg>`,
            humidity: `<svg viewBox="0 0 24 24" fill="none" class="w-full h-full"><path d="M12 2.5 C12 2.5 5 11 5 16 A 7 7 0 0 0 19 16 C19 11 12 2.5 12 2.5 Z" fill="#0284C7" stroke="#38BDF8" stroke-width="1.6"/><path d="M9 14.5 A 3.5 3.5 0 0 0 12 18" stroke="#FFFFFF" stroke-width="1.4" stroke-linecap="round" opacity="0.8"/></svg>`,
            uv: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`,
            sun: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 18h18"/><path d="M7 18a5 5 0 0 1 10 0"/><path d="M12 7V4M17 9l2-2M7 9L5 7"/></svg>`,
            pressure: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 1.5"/><path d="M9 3h6"/></svg>`,
            leaf: `<svg viewBox="0 0 24 24" fill="none" class="w-full h-full"><path d="M4 20 C6 14 11 9 19 5 C19 13 14 18 8 20 Z" fill="#10B981" stroke="#34D399" stroke-width="1.5"/><path d="M7 17 C10 13 13 10 17 7" stroke="#FFFFFF" stroke-width="1.3" stroke-linecap="round" opacity="0.8"/></svg>`,
            clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>`,
            calendar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="3" y="4" width="18" height="17" rx="3"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><circle cx="8" cy="14" r="1" fill="currentColor"/><circle cx="12" cy="14" r="1" fill="currentColor"/><circle cx="16" cy="14" r="1" fill="currentColor"/></svg>`,
            pin: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 21c-4-4.5-7-8.5-7-12a7 7 0 0 1 14 0c0 3.5-3 7.5-7 12z"/><circle cx="12" cy="9" r="2.5" fill="currentColor"/></svg>`,
            home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 10.5L12 3l9 7.5V20a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9.5z"/><path d="M9 22V12h6v10"/></svg>`,
            globe: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a14.5 14.5 0 0 1 0 18a14.5 14.5 0 0 1 0-18z"/></svg>`,
            gear: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
            city: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M3 21h18M5 21V7l8-4v18M13 10l6 3v8M9 9v.01M9 13v.01M9 17v.01M17 15v.01M17 18v.01"/></svg>`,
            bot: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="5" y="4" width="14" height="16" rx="3"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/><path d="M9 14h6"/><path d="M12 1v3"/></svg>`,
            bell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
            alert: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
            refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>`,
            trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
            dropSmall: `<svg viewBox="0 0 16 16" fill="currentColor" class="w-2.5 h-2.5 inline-block"><path d="M8 2 C8 2 3.5 7.5 3.5 11 A 4.5 4.5 0 0 0 12.5 11 C12.5 7.5 8 2 8 2 Z"/></svg>`,
        };

        // Volumetric 3D Weather Illustrations (Self-contained SVG system)
        const WeatherIcons = {
            clearDay: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <radialGradient id="cd_sun" cx="35%" cy="35%" r="65%">
                            <stop offset="0%" stop-color="#FFF7B2"/>
                            <stop offset="35%" stop-color="#FBBF24"/>
                            <stop offset="80%" stop-color="#F59E0B"/>
                            <stop offset="100%" stop-color="#D97706"/>
                        </radialGradient>
                        <radialGradient id="cd_corona" cx="50%" cy="50%" r="50%">
                            <stop offset="45%" stop-color="#F59E0B" stop-opacity="0.35"/>
                            <stop offset="100%" stop-color="#F59E0B" stop-opacity="0"/>
                        </radialGradient>
                    </defs>
                    <circle cx="32" cy="32" r="28" fill="url(#cd_corona)"/>
                    <g stroke="#F59E0B" stroke-width="3" stroke-linecap="round" opacity="0.9">
                        <line x1="32" y1="8" x2="32" y2="3"/>
                        <line x1="32" y1="61" x2="32" y2="56"/>
                        <line x1="8" y1="32" x2="3" y2="32"/>
                        <line x1="61" y1="32" x2="56" y2="32"/>
                        <line x1="15" y1="15" x2="11" y2="11"/>
                        <line x1="53" y1="53" x2="49" y2="49"/>
                        <line x1="15" y1="49" x2="11" y2="53"/>
                        <line x1="53" y1="11" x2="49" y2="15"/>
                    </g>
                    <circle cx="32" cy="32" r="18" fill="url(#cd_sun)"/>
                    <path d="M23 21 A 12 12 0 0 1 38 20" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" opacity="0.65"/>
                </svg>`,

            clearNight: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="cn_moon" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#FEF08A"/>
                            <stop offset="50%" stop-color="#FCD34D"/>
                            <stop offset="100%" stop-color="#F59E0B"/>
                        </linearGradient>
                        <radialGradient id="cn_glow" cx="45%" cy="45%" r="55%">
                            <stop offset="0%" stop-color="#FDE047" stop-opacity="0.35"/>
                            <stop offset="100%" stop-color="#FDE047" stop-opacity="0"/>
                        </radialGradient>
                    </defs>
                    <circle cx="32" cy="32" r="26" fill="url(#cn_glow)"/>
                    <path d="M16 16 L17.5 20 L21.5 21.5 L17.5 23 L16 27 L14.5 23 L10.5 21.5 L14.5 20 Z" fill="#FDE047" opacity="0.85"/>
                    <circle cx="48" cy="18" r="1.5" fill="#FEF08A" opacity="0.9"/>
                    <circle cx="18" cy="46" r="1.5" fill="#FEF08A" opacity="0.7"/>
                    <path d="M38 12 C24 13 14 24 14 38 C14 49 22 57 33 58 C25 53 23 41 27 30 C30 22 36 16 45 14 C42.5 12.8 40.3 12.2 38 12 Z" 
                          fill="url(#cn_moon)"/>
                    <circle cx="25" cy="36" r="2" fill="#D97706" opacity="0.25"/>
                    <circle cx="28" cy="45" r="3" fill="#D97706" opacity="0.2"/>
                    <circle cx="32" cy="26" r="1.8" fill="#D97706" opacity="0.2"/>
                </svg>`,

            partlyCloudyDay: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <radialGradient id="pcd_sun" cx="35%" cy="35%" r="65%">
                            <stop offset="0%" stop-color="#FFF7B2"/>
                            <stop offset="40%" stop-color="#FBBF24"/>
                            <stop offset="85%" stop-color="#F59E0B"/>
                            <stop offset="100%" stop-color="#D97706"/>
                        </radialGradient>
                        <linearGradient id="pcd_cloud" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#FFFFFF"/>
                            <stop offset="65%" stop-color="#F1F5F9"/>
                            <stop offset="100%" stop-color="#CBD5E1"/>
                        </linearGradient>
                        <linearGradient id="pcd_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.22"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <circle cx="42" cy="24" r="13" fill="url(#pcd_sun)"/>
                    <g stroke="#F59E0B" stroke-width="2.2" stroke-linecap="round" opacity="0.85">
                        <line x1="42" y1="7" x2="42" y2="4"/>
                        <line x1="57" y1="17" x2="60" y2="15"/>
                        <line x1="59" y1="30" x2="62" y2="31"/>
                        <line x1="54" y1="9" x2="56" y2="7"/>
                    </g>
                    <ellipse cx="34" cy="50" rx="19" ry="3" fill="url(#pcd_shadow)"/>
                    <path d="M22 49 C15 49 10 44 10 38 C10 32.5 14 28 19.5 27.5 C21.5 20 28 15 35.5 15 C43.5 15 50 20.5 51.5 28 C56 29 59 33 59 38 C59 44 54 49 48 49 Z" 
                          fill="url(#pcd_cloud)"/>
                    <path d="M28 21 C32 18 39 18 43 22" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" opacity="0.8"/>
                    <path d="M14 35 C14 31 17 29 20 29" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" opacity="0.6"/>
                </svg>`,

            partlyCloudyNight: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="pcn_moon" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#FEF08A"/>
                            <stop offset="50%" stop-color="#FCD34D"/>
                            <stop offset="100%" stop-color="#F59E0B"/>
                        </linearGradient>
                        <linearGradient id="pcn_cloud" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#FFFFFF"/>
                            <stop offset="65%" stop-color="#E2E8F0"/>
                            <stop offset="100%" stop-color="#94A3B8"/>
                        </linearGradient>
                        <linearGradient id="pcn_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.25"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <path d="M43 14 C35 15 29 21 29 29 C29 34 31 38 35 41 C31 38 30 31 33 24 C35 19 39 15 45 14 Z" 
                          fill="url(#pcn_moon)"/>
                    <circle cx="50" cy="18" r="1.5" fill="#FEF08A" opacity="0.85"/>
                    <ellipse cx="34" cy="50" rx="19" ry="3" fill="url(#pcn_shadow)"/>
                    <path d="M22 49 C15 49 10 44 10 38 C10 32.5 14 28 19.5 27.5 C21.5 20 28 15 35.5 15 C43.5 15 50 20.5 51.5 28 C56 29 59 33 59 38 C59 44 54 49 48 49 Z" 
                          fill="url(#pcn_cloud)"/>
                    <path d="M28 21 C32 18 39 18 43 22" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" opacity="0.7"/>
                </svg>`,

            cloudy: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="c_back" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#CBD5E1"/>
                            <stop offset="100%" stop-color="#64748B"/>
                        </linearGradient>
                        <linearGradient id="c_front" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#FFFFFF"/>
                            <stop offset="65%" stop-color="#F1F5F9"/>
                            <stop offset="100%" stop-color="#CBD5E1"/>
                        </linearGradient>
                        <linearGradient id="c_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.22"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <path d="M30 40 C25 40 21 36 21 32 C21 27.5 24 24 28.5 23.5 C30 18 35 14 41 14 C47.5 14 53 18.5 54 24.5 C58 25.5 60 28.5 60 32.5 C60 37 56 40 51 40 Z" 
                          fill="url(#c_back)" opacity="0.9"/>
                    <ellipse cx="32" cy="51" rx="21" ry="3.5" fill="url(#c_shadow)"/>
                    <path d="M18 50 C12 50 8 45.5 8 40 C8 35 12 31 16.5 30.5 C18.5 23.5 24.5 19 31.5 19 C39 19 45 24 46.5 30.5 C50.5 31.5 53 35 53 39.5 C53 45 48.5 50 43 50 Z" 
                          fill="url(#c_front)"/>
                    <path d="M25 24 C28 22 34 22 38 25" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" opacity="0.75"/>
                </svg>`,

            rainLight: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="rl_cloud" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#FFFFFF"/>
                            <stop offset="65%" stop-color="#F1F5F9"/>
                            <stop offset="100%" stop-color="#CBD5E1"/>
                        </linearGradient>
                        <linearGradient id="rl_drop" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#38BDF8"/>
                            <stop offset="100%" stop-color="#0284C7"/>
                        </linearGradient>
                        <linearGradient id="rl_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.2"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <ellipse cx="32" cy="42" rx="20" ry="3" fill="url(#rl_shadow)"/>
                    <path d="M20 41 C14 41 10 37 10 32 C10 27.5 13.5 24 18 23.5 C20 17 26 13 32.5 13 C39.5 13 45 17.5 46.5 23.5 C50.5 24.5 53 27.5 53 32 C53 37 49 41 43.5 41 Z" 
                          fill="url(#rl_cloud)"/>
                    <path d="M26 18 C29 16 35 16 38 19" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" opacity="0.75"/>
                    <path d="M20 47 C20 45 22 43 22 43 C22 43 24 45 24 47 C24 48.5 23 50 22 50 C21 50 20 48.5 20 47 Z" fill="url(#rl_drop)"/>
                    <path d="M31 50 C31 48 33 46 33 46 C33 46 35 48 35 50 C35 51.5 34 53 33 53 C32 53 31 51.5 31 50 Z" fill="url(#rl_drop)"/>
                    <path d="M42 46 C42 44 44 42 44 42 C44 42 46 44 46 46 C46 47.5 45 49 44 49 C43 49 42 47.5 42 46 Z" fill="url(#rl_drop)"/>
                </svg>`,

            rainHeavy: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="rh_cloud" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#64748B"/>
                            <stop offset="60%" stop-color="#334155"/>
                            <stop offset="100%" stop-color="#1E293B"/>
                        </linearGradient>
                        <linearGradient id="rh_streak" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#38BDF8"/>
                            <stop offset="100%" stop-color="#0284C7"/>
                        </linearGradient>
                        <linearGradient id="rh_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.25"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <ellipse cx="32" cy="38" rx="20" ry="3" fill="url(#rh_shadow)"/>
                    <path d="M20 37 C14 37 10 33 10 28 C10 23.5 13.5 20 18 19.5 C20 13 26 9 32.5 9 C39.5 9 45 13.5 46.5 19.5 C50.5 20.5 53 23.5 53 28 C53 33 49 37 43.5 37 Z" 
                          fill="url(#rh_cloud)"/>
                    <path d="M26 14 C29 12 35 12 38 15" stroke="#CBD5E1" stroke-width="1.8" stroke-linecap="round" opacity="0.6"/>
                    <g stroke="url(#rh_streak)" stroke-width="2.5" stroke-linecap="round">
                        <line x1="18" y1="44" x2="14" y2="54"/>
                        <line x1="26" y1="44" x2="22" y2="56"/>
                        <line x1="34" y1="44" x2="30" y2="56"/>
                        <line x1="42" y1="44" x2="38" y2="56"/>
                        <line x1="49" y1="44" x2="46" y2="52"/>
                    </g>
                </svg>`,

            thunderstorm: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="ts_cloud" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#64748B"/>
                            <stop offset="60%" stop-color="#334155"/>
                            <stop offset="100%" stop-color="#1E293B"/>
                        </linearGradient>
                        <linearGradient id="ts_bolt" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#FEF08A"/>
                            <stop offset="50%" stop-color="#FACC15"/>
                            <stop offset="100%" stop-color="#EAB308"/>
                        </linearGradient>
                        <linearGradient id="ts_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.3"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <ellipse cx="32" cy="36" rx="20" ry="3" fill="url(#ts_shadow)"/>
                    <path d="M20 35 C14 35 10 31 10 26 C10 21.5 13.5 18 18 17.5 C20 11 26 7 32.5 7 C39.5 7 45 11.5 46.5 17.5 C50.5 18.5 53 21.5 53 26 C53 31 49 35 43.5 35 Z" 
                          fill="url(#ts_cloud)"/>
                    <path d="M26 12 C29 10 35 10 38 13" stroke="#94A3B8" stroke-width="1.8" stroke-linecap="round" opacity="0.6"/>
                    <polygon points="34,25 23,39 30,39 26,56 41,36 33,36 38,25" 
                             fill="url(#ts_bolt)"/>
                    <line x1="15" y1="44" x2="12" y2="52" stroke="#38BDF8" stroke-width="2" stroke-linecap="round"/>
                    <line x1="48" y1="43" x2="45" y2="51" stroke="#38BDF8" stroke-width="2" stroke-linecap="round"/>
                </svg>`,

            snow: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="sn_cloud" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#FFFFFF"/>
                            <stop offset="65%" stop-color="#F1F5F9"/>
                            <stop offset="100%" stop-color="#CBD5E1"/>
                        </linearGradient>
                        <linearGradient id="sn_shadow" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0F172A" stop-opacity="0.22"/>
                            <stop offset="100%" stop-color="#0F172A" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <ellipse cx="32" cy="38" rx="20" ry="3" fill="url(#sn_shadow)"/>
                    <path d="M20 37 C14 37 10 33 10 28 C10 23.5 13.5 20 18 19.5 C20 13 26 9 32.5 9 C39.5 9 45 13.5 46.5 19.5 C50.5 20.5 53 23.5 53 28 C53 33 49 37 43.5 37 Z" 
                          fill="url(#sn_cloud)"/>
                    <path d="M26 14 C29 12 35 12 38 15" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" opacity="0.8"/>
                    <g stroke="#BAE6FD" stroke-width="2" stroke-linecap="round">
                        <g transform="translate(32, 48)">
                            <line x1="0" y1="-5" x2="0" y2="5"/>
                            <line x1="-5" y1="0" x2="5" y2="0"/>
                            <line x1="-3.5" y1="-3.5" x2="3.5" y2="3.5"/>
                            <line x1="-3.5" y1="3.5" x2="3.5" y2="-3.5"/>
                            <circle cx="0" cy="0" r="1" fill="#FFFFFF"/>
                        </g>
                        <g transform="translate(20, 46)">
                            <line x1="0" y1="-3.5" x2="0" y2="3.5"/>
                            <line x1="-3.5" y1="0" x2="3.5" y2="0"/>
                            <line x1="-2.5" y1="-2.5" x2="2.5" y2="2.5"/>
                            <line x1="-2.5" y1="2.5" x2="2.5" y2="-2.5"/>
                        </g>
                        <g transform="translate(44, 46)">
                            <line x1="0" y1="-3.5" x2="0" y2="3.5"/>
                            <line x1="-3.5" y1="0" x2="3.5" y2="0"/>
                            <line x1="-2.5" y1="-2.5" x2="2.5" y2="2.5"/>
                            <line x1="-2.5" y1="2.5" x2="2.5" y2="-2.5"/>
                        </g>
                    </g>
                </svg>`,

            fog: (cls) => `
                <svg viewBox="0 0 64 64" fill="none" class="${cls}">
                    <defs>
                        <linearGradient id="fog_g1" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="#94A3B8" stop-opacity="0.2"/>
                            <stop offset="35%" stop-color="#E2E8F0" stop-opacity="0.95"/>
                            <stop offset="70%" stop-color="#CBD5E1" stop-opacity="0.9"/>
                            <stop offset="100%" stop-color="#94A3B8" stop-opacity="0.2"/>
                        </linearGradient>
                        <linearGradient id="fog_g2" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="#94A3B8" stop-opacity="0.1"/>
                            <stop offset="40%" stop-color="#FFFFFF" stop-opacity="0.95"/>
                            <stop offset="75%" stop-color="#E2E8F0" stop-opacity="0.85"/>
                            <stop offset="100%" stop-color="#94A3B8" stop-opacity="0.1"/>
                        </linearGradient>
                    </defs>
                    <path d="M12 20 C18 16 26 24 34 20 C42 16 50 22 54 20" stroke="url(#fog_g1)" stroke-width="4" stroke-linecap="round"/>
                    <path d="M8 29 C16 25 24 33 32 29 C40 25 48 31 56 29" stroke="url(#fog_g2)" stroke-width="4.5" stroke-linecap="round"/>
                    <path d="M14 38 C20 34 28 42 36 38 C44 34 52 40 54 38" stroke="url(#fog_g1)" stroke-width="4" stroke-linecap="round"/>
                    <path d="M10 47 C17 43 25 51 33 47 C41 43 49 49 55 47" stroke="url(#fog_g2)" stroke-width="4" stroke-linecap="round"/>
                </svg>`,

            getAqiCenterLeaf: (color) => `
                <svg viewBox="0 0 24 24" fill="none" class="w-full h-full">
                    <path d="M4 20 C6 14 11 9 19 5 C19 13 14 18 8 20 Z" fill="${color}" fill-opacity="0.9" stroke="#FFFFFF" stroke-width="1.3"/>
                    <path d="M7 17 C10 13 13 10 17 7" stroke="#FFFFFF" stroke-width="1.3" stroke-linecap="round" opacity="0.85"/>
                </svg>`,

            get: function(code, isNight = false, cls = "w-full h-full") {
                const c = Number(code) || 0;
                if (c === 0) return isNight ? this.clearNight(cls) : this.clearDay(cls);
                if (c === 1 || c === 2) return isNight ? this.partlyCloudyNight(cls) : this.partlyCloudyDay(cls);
                if (c === 3) return this.cloudy(cls);
                if (c === 45 || c === 48) return this.fog(cls);
                if ([51, 53, 55, 61, 80].includes(c)) return this.rainLight(cls);
                if ([63, 65, 81, 82].includes(c)) return this.rainHeavy(cls);
                if ([71, 73, 75, 77, 85, 86].includes(c)) return this.snow(cls);
                if ([95, 96, 99].includes(c)) return this.thunderstorm(cls);
                return isNight ? this.partlyCloudyNight(cls) : this.partlyCloudyDay(cls);
            }
        };

        // Full UI Translation Dictionary (Clean labels with custom SVGs)
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
                lblAlert: "Xavfli havo xabarlari",
                lblAlertDesc: "AQI zararli darajaga yetganda avtomatik ogohlantirish",
                lblDigest: "Ertalabki xabar",
                lblDigestDesc: "Har tong kungi ob-havo va havo sifati ma'lumoti",
                secSchedule: "Vaqt va mintaqa",
                lblDigestTime: "Xabar yuborish vaqti",
                lblTimezone: "Vaqt mintaqasi",
                secHome: "Asosiy uy hududi",
                lblHomeDesc: "Boshqa shahar yoki viloyatga borganingizda ham ertalabki xabarlar va ogohlantirishlar aynan uy hududingiz bo'yicha yuboriladi.",
                lblYourHome: "Uy hududingiz:",
                btnSetHome: "Joriy hududni uy qilish",
                btnClearHome: "O'chirish",
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
                lblAlert: "Опасный воздух",
                lblAlertDesc: "Автоматическое оповещение при опасном AQI",
                lblDigest: "Утренний дайджест",
                lblDigestDesc: "Ежедневная утренняя сводка погоды и воздуха",
                secSchedule: "Время и часовой пояс",
                lblDigestTime: "Время отправки",
                lblTimezone: "Часовой пояс",
                secHome: "Домашний регион",
                lblHomeDesc: "Даже во время поездок уведомления и сводки будут приходить по вашему домашнему району.",
                lblYourHome: "Ваш дом:",
                btnSetHome: "Сделать текущий домашним",
                btnClearHome: "Удалить",
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
                lblAlert: "Hazardous Air Alerts",
                lblAlertDesc: "Automatic alert when AQI reaches unhealthy levels",
                lblDigest: "Daily Morning Digest",
                lblDigestDesc: "Daily morning forecast and air quality summary",
                secSchedule: "Schedule & Timezone",
                lblDigestTime: "Digest Delivery Time",
                lblTimezone: "Timezone",
                secHome: "Home District",
                lblHomeDesc: "Morning digests and hazardous air alerts are always delivered for your home district, even when traveling.",
                lblYourHome: "Home district:",
                btnSetHome: "Set current as Home",
                btnClearHome: "Clear",
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
            const labels = { uz: 'UZ', ru: 'RU', en: 'EN' };
            const labelEl = document.getElementById('currentLangLabel');
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
            const btnSetHomeEl = document.getElementById('btnSetCurrentAsHomeText');
            if (btnSetHomeEl) btnSetHomeEl.textContent = t.btnSetHome;
            const btnClearHomeEl = document.getElementById('btnClearHomeText');
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

            // 2. Weather Hero (3D Volumetric Icon)
            const nowH = new Date().getHours();
            const isNight = (weather.is_day !== undefined) ? !weather.is_day : (nowH < 6 || nowH >= 20);
            const heroIconEl = document.getElementById('weatherIconHero');
            if (heroIconEl) {
                heroIconEl.innerHTML = WeatherIcons.get(weather.weather_code, isNight, 'w-24 h-24');
            }
            document.getElementById('weatherTemp').innerHTML = `<span>${Math.round(weather.temp)}</span><span class="text-4xl font-normal mt-1 text-white/80">°</span>`;
            document.getElementById('weatherCondition').textContent = weather.description || weather.condition;
            document.getElementById('tempRange').textContent = `${t.max}: ${Math.round(weather.temp_max)}° • ${t.min}: ${Math.round(weather.temp_min)}°`;
            document.getElementById('feelsLike').textContent = `${t.feelsLike}: ${Math.round(weather.feels_like)}°`;

            // Weather theme
            setWeatherTheme(weather.weather_code, isNight);

            // 3. AQI Card & Center Gauge Icon
            document.getElementById('aqiNumber').textContent = air.aqi;
            const badge = document.getElementById('aqiLevelBadge');
            badge.textContent = air.level_name;
            badge.style.backgroundColor = `${air.color}35`;
            badge.style.color = air.color;
            badge.style.borderColor = `${air.color}50`;

            document.getElementById('aqiAdviceText').textContent = air.advice;
            document.getElementById('aqiUpdatedTime').textContent = air.updated_at || '--:--';
            
            const aqiCenterIcon = document.getElementById('aqiGaugeCenterIcon');
            if (aqiCenterIcon) {
                aqiCenterIcon.innerHTML = WeatherIcons.getAqiCenterLeaf(air.color);
            }

            // AQI circular stroke (max 300 AQI for full circle, 251.2 dasharray)
            const circle = document.getElementById('aqiProgressCircle');
            const percent = Math.min(1, air.aqi / 300);
            const offset = 251.2 - (percent * 251.2);
            circle.style.stroke = air.color;
            circle.style.strokeDashoffset = offset;

            // Pollutants
            document.getElementById('valPm25').innerHTML = `${air.pm2_5 !== null ? air.pm2_5 : '—'} <span class="text-[10px] text-white/60 font-normal">µg/m³</span>`;
            document.getElementById('valPm10').innerHTML = `${air.pm10 !== null ? air.pm10 : '—'} <span class="text-[10px] text-white/60 font-normal">µg/m³</span>`;

            // 4. Hourly Forecast (3D Icons & Today vs Tomorrow clear differentiation)
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
                    const isItemNight = (hourNum < 6 || hourNum >= 20);

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

                    const hourlyIconSvg = WeatherIcons.get(item.weather_code ?? weather.weather_code, isItemNight, 'w-8 h-8');

                    return `
                    <div class="flex-shrink-0 w-[68px] py-2.5 px-1.5 rounded-2xl flex flex-col items-center justify-between text-center transition ${cardBg}">
                        <div class="flex flex-col items-center w-full leading-tight">
                            <span class="text-[9px] ${badgeClass} uppercase tracking-tight truncate w-full">${dayBadge}</span>
                            <span class="text-[11px] font-bold ${item.is_now ? 'text-white' : 'text-white/85'} mt-0.5">${item.is_now ? t.now : item.time}</span>
                        </div>
                        <div class="w-8 h-8 my-1 flex items-center justify-center">
                            ${hourlyIconSvg}
                        </div>
                        <span class="text-sm font-bold font-sans">${Math.round(item.temp)}°</span>
                        ${item.pop > 10 ? `<span class="text-[9px] font-bold text-sky-300 mt-0.5 flex items-center gap-0.5 justify-center">${AppIcons.dropSmall}<span>${item.pop}%</span></span>` : ''}
                    </div>
                    `;
                }).join('');
            }

            // 5. Weekly Forecast (3D Icons & Dynamic for ANY temperature range)
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
                    const weeklyIconSvg = WeatherIcons.get(day.weather_code ?? 0, false, 'w-6 h-6');

                    return `
                    <div class="py-2.5 flex items-center justify-between text-xs font-medium">
                        <span class="w-16 font-semibold truncate ${isToday ? 'text-sky-300 font-bold' : 'text-white'}">${dayLabel}</span>
                        <div class="w-8 h-8 flex items-center justify-center flex-shrink-0">
                            ${weeklyIconSvg}
                        </div>
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
            document.getElementById('valWindDir').textContent = weather.wind_dir || weather.wind_direction;
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
                        <span class="flex items-center gap-2"><span class="w-3.5 h-3.5 text-rose-400 flex items-center justify-center flex-shrink-0">${AppIcons.pin}</span> <span>${d.name}</span></span>
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
                        <span class="flex items-center gap-2"><span class="w-3.5 h-3.5 text-rose-400 flex items-center justify-center flex-shrink-0">${AppIcons.pin}</span> <span>${d.name}</span></span>
                        ${d.id === currentDistrictId ? '<span class="text-sky-300">✓</span>' : `<span class="text-white/30 text-xs">${t.select}</span>`}
                    </button>
                `).join('');
            }

            // 2. Global search results
            if (globalSearchResults.length > 0) {
                html += `<div class="text-[10px] font-bold text-amber-300 uppercase tracking-wider px-1 pt-2 pb-0.5 flex items-center gap-1.5"><span class="w-3.5 h-3.5 text-sky-400 flex items-center justify-center flex-shrink-0">${AppIcons.globe}</span> <span>${t.globalResultsTitle}</span></div>`;
                html += globalSearchResults.map((loc, idx) => `
                    <button onclick="selectGlobalLocation(${idx})" class="w-full text-left p-3 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-sky-400/30 transition flex items-center justify-between">
                        <div class="flex items-center gap-2.5 truncate pr-2">
                            <span class="w-5 h-5 text-sky-400 flex items-center justify-center flex-shrink-0">${AppIcons.globe}</span>
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
