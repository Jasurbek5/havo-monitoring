"""Admin panel: Bot foydalanuvchilarini ko'rish va monitoring qilish."""

import html
import secrets
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.session import get_session_factory
from app.models import User

security = HTTPBasic()


def authenticate_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """HTTP Basic Auth orqali adminni tekshirish."""
    settings = get_settings()
    correct_user = secrets.compare_digest(credentials.username, settings.admin_username)
    correct_pass = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Noto'g'ri login yoki parol",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(authenticate_admin)],
)


def _format_dt(dt: datetime | None, tz: ZoneInfo) -> str:
    if dt is None:
        return "—"
    try:
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M")


def _lang_badge(lang: str) -> str:
    lang = (lang or "uz").lower()
    badges = {
        "uz": ("🇺🇿", "O'zbekcha", "#0284c7"),
        "ru": ("🇷🇺", "Русский", "#9333ea"),
        "en": ("🇬🇧", "English", "#d97706"),
    }
    flag, name, color = badges.get(lang, ("🌐", lang.upper(), "#64748b"))
    return f'<span class="badge" style="background: {color}20; color: {color}; border-color: {color}40;">{flag} {name}</span>'


def _country_flag(country: str | None) -> str:
    if not country:
        return "📍"
    c = country.lower().strip()
    if any(k in c for k in ("uzbek", "o'zbek", "узбек")):
        return "🇺🇿"
    if any(k in c for k in ("korea", "коре", "seoul")):
        return "🇰🇷"
    if any(k in c for k in ("turk", "турц", "istanbul")):
        return "🇹🇷"
    if any(k in c for k in ("russia", "росси")):
        return "🇷🇺"
    if any(k in c for k in ("kazakh", "қазақ", "казах")):
        return "🇰🇿"
    if any(k in c for k in ("united states", "usa", "amerika", "сша")):
        return "🇺🇸"
    if any(k in c for k in ("emirates", "dubai", "baa", "uae", "оаэ")):
        return "🇦🇪"
    if any(k in c for k in ("japan", "yaponi", "япон")):
        return "🇯🇵"
    if any(k in c for k in ("united kingdom", "uk", "britan", "angli", "великобрита")):
        return "🇬🇧"
    if any(k in c for k in ("china", "xitoy", "китай")):
        return "🇨🇳"
    if any(k in c for k in ("germany", "nemis", "germani", "герман")):
        return "🇩🇪"
    return "🌐"


def _render_admin_html(users: list[User], tz: ZoneInfo) -> str:
    total_users = len(users)
    active_users = sum(1 for u in users if u.is_active)
    alert_users = sum(1 for u in users if u.alert_enabled)
    digest_users = sum(1 for u in users if u.daily_digest)
    with_loc_users = sum(1 for u in users if (u.district_id or u.home_district_id))

    # Top Global Shaharlar
    city_counter = Counter()
    for u in users:
        d = u.district or u.home_district
        if d:
            flag = _country_flag(d.country)
            c_tag = f" ({d.country})" if d.country else ""
            city_counter[f"{flag} {d.name_uz}{c_tag}"] += 1
    top_cities = city_counter.most_common(5)
    top_cities_html = " • ".join(
        f'<span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); font-size: 0.8rem; margin: 2px;">{html.escape(c[0])}: <b>{c[1]}</b></span>'
        for c in top_cities
    ) if top_cities else '<span class="text-muted">Hozircha ma\'lumot yo\'q</span>'

    rows_html = []
    for idx, u in enumerate(users, 1):
        if u.district:
            flag = _country_flag(u.district.country)
            c_part = f", {u.district.country}" if u.district.country else ""
            cur_display = f"{flag} {u.district.name_uz}{c_part}"
            cur_html = f'<span class="district-tag">📍 {html.escape(cur_display)}</span>'
        else:
            cur_display = "tanlanmagan"
            cur_html = '<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8; border-color: rgba(148, 163, 184, 0.25);">Tanlanmagan</span>'

        if u.home_district:
            h_flag = _country_flag(u.home_district.country)
            h_part = f", {u.home_district.country}" if u.home_district.country else ""
            home_display = f"{h_flag} {u.home_district.name_uz}{h_part}"
            home_html = f'<span class="district-tag home-tag">🏠 {html.escape(home_display)}</span>'
        else:
            home_display = "—"
            home_html = '<span class="text-muted">—</span>'

        saved_badges = []
        saved_search_parts = []
        for loc in (getattr(u, "saved_locations", []) or []):
            d = loc.district
            if not d:
                continue
            is_h = loc.is_home
            prefix = "🏠 " if is_h else "📍 "
            s_name = d.name_uz
            saved_search_parts.append(s_name.lower())
            if d.country:
                saved_search_parts.append(d.country.lower())
            tag_border = "border-color: rgba(251, 191, 36, 0.4); color: #fde047;" if is_h else ""
            saved_badges.append(
                f'<span class="district-tag" style="font-size: 0.725rem; padding: 2px 7px; border-radius: 6px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); {tag_border}">'
                f'{prefix}{html.escape(s_name)}'
                f'</span>'
            )
        saved_html = f'<div style="display: flex; flex-wrap: wrap; gap: 4px; max-width: 240px;">{"".join(saved_badges)}</div>' if saved_badges else '<span class="text-muted">—</span>'

        status_badge = (
            '<span class="badge badge-success">🟢 Faol</span>'
            if u.is_active
            else '<span class="badge badge-danger">🔴 Bloklagan</span>'
        )
        alert_badge = (
            '<span class="pill pill-success" title="Xavfli havo ogohlantirishi yoqilgan">🚨 Yoqilgan</span>'
            if u.alert_enabled
            else '<span class="pill pill-muted">O\'chirilgan</span>'
        )
        digest_badge = (
            f'<span class="pill pill-info" title="Ertalabki xabarnoma vaqti: {html.escape(u.digest_time or "07:00")}">'
            f'☀️ {html.escape(u.digest_time or "07:00")}</span>'
            if u.daily_digest
            else '<span class="pill pill-muted">O\'chirilgan</span>'
        )
        tz_str = html.escape(u.timezone or "auto")
        created_str = _format_dt(u.created_at, tz)
        lang_html = _lang_badge(u.language)
        search_blob = f"{u.telegram_id} {cur_display.lower()} {home_display.lower()} {' '.join(saved_search_parts)} {tz_str.lower()}"

        rows_html.append(f"""
        <tr data-status="{'active' if u.is_active else 'inactive'}"
            data-lang="{html.escape(u.language or 'uz')}"
            data-search="{html.escape(search_blob)}">
            <td class="text-muted">{idx}</td>
            <td>
                <span class="tg-id font-mono">{u.telegram_id}</span>
            </td>
            <td>{lang_html}</td>
            <td>{cur_html}</td>
            <td>{home_html}</td>
            <td>{saved_html}</td>
            <td><code class="tz-code">{tz_str}</code></td>
            <td>
                <div class="notifications-cell">
                    {alert_badge}
                    {digest_badge}
                </div>
            </td>
            <td>{status_badge}</td>
            <td class="text-muted text-sm">{created_str}</td>
        </tr>
        """)

    table_rows = "".join(rows_html) if rows_html else """
        <tr>
            <td colspan="10" class="empty-state">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">👥</div>
                <p>Hozircha botda foydalanuvchilar yo'q</p>
            </td>
        </tr>
    """

    return f"""<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Havo Monitoring - Admin Panel</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #27354a;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #10b981;
            --primary-glow: rgba(16, 185, 129, 0.2);
            --danger: #ef4444;
            --info: #06b6d4;
            --warning: #f59e0b;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            min-height: 100vh;
            padding: 1.5rem;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        /* Header */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
            margin-bottom: 1.5rem;
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .brand-icon {{
            font-size: 1.75rem;
            background: var(--surface);
            padding: 0.5rem 0.65rem;
            border-radius: 0.75rem;
            border: 1px solid var(--border);
        }}
        .brand h1 {{
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}
        .brand p {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: var(--surface);
            color: var(--text);
            border: 1px solid var(--border);
            padding: 0.55rem 1rem;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s ease;
        }}
        .btn:hover {{
            background: var(--surface-hover);
            border-color: #475569;
        }}
        .btn-primary {{
            background: var(--primary);
            color: #022c22;
            border-color: var(--primary);
            font-weight: 600;
        }}
        .btn-primary:hover {{
            background: #059669;
            color: #ffffff;
        }}
        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            position: relative;
            overflow: hidden;
        }}
        .stat-card::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--primary);
            opacity: 0.6;
        }}
        .stat-card.alert-card::after {{ background: var(--danger); }}
        .stat-card.digest-card::after {{ background: var(--info); }}
        .stat-title {{
            font-size: 0.825rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .stat-value {{
            font-size: 1.85rem;
            font-weight: 700;
        }}
        /* Search & Filter Bar */
        .controls-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            padding: 1rem;
            margin-bottom: 1.25rem;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            align-items: center;
            justify-content: space-between;
        }}
        .search-box {{
            flex: 1;
            min-width: 250px;
            position: relative;
        }}
        .search-box input {{
            width: 100%;
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.6rem 0.85rem 0.6rem 2.25rem;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            outline: none;
            transition: border-color 0.2s;
        }}
        .search-box input:focus {{
            border-color: var(--primary);
            box-shadow: 0 0 0 2px var(--primary-glow);
        }}
        .search-icon {{
            position: absolute;
            left: 0.75rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            pointer-events: none;
        }}
        .filters {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}
        .filter-select {{
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.6rem 0.85rem;
            border-radius: 0.5rem;
            font-size: 0.85rem;
            outline: none;
            cursor: pointer;
        }}
        /* Table Card */
        .table-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .table-responsive {{
            overflow-x: auto;
            width: 100%;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.875rem;
        }}
        thead {{
            background: #172033;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            padding: 0.85rem 1rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
            white-space: nowrap;
        }}
        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
            vertical-align: middle;
        }}
        tbody tr:hover {{
            background: var(--surface-hover);
        }}
        tbody tr:last-child td {{
            border-bottom: none;
        }}
        /* Badges & Elements */
        .font-mono {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}
        .tg-id {{
            background: #0f172a;
            padding: 0.25rem 0.5rem;
            border-radius: 0.35rem;
            font-size: 0.825rem;
            border: 1px solid #334155;
            color: #38bdf8;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.25rem 0.55rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid transparent;
            white-space: nowrap;
        }}
        .badge-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border-color: rgba(16, 185, 129, 0.3);
        }}
        .badge-danger {{
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.3);
        }}
        .pill {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 0.35rem;
            font-size: 0.75rem;
            font-weight: 500;
            white-space: nowrap;
        }}
        .pill-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.25);
        }}
        .pill-info {{
            background: rgba(6, 182, 212, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(6, 182, 212, 0.25);
        }}
        .pill-muted {{
            background: rgba(148, 163, 184, 0.1);
            color: #64748b;
        }}
        .district-tag {{
            display: inline-block;
            font-weight: 500;
            color: #e2e8f0;
        }}
        .home-tag {{
            color: #cbd5e1;
        }}
        .tz-code {{
            background: #0f172a;
            color: #cbd5e1;
            padding: 0.2rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.775rem;
        }}
        .notifications-cell {{
            display: flex;
            gap: 0.35rem;
            flex-wrap: wrap;
        }}
        .text-muted {{ color: var(--text-muted); }}
        .text-sm {{ font-size: 0.8rem; }}
        .empty-state {{
            text-align: center;
            padding: 3rem 1rem;
            color: var(--text-muted);
        }}
        .table-footer {{
            padding: 0.75rem 1rem;
            background: #172033;
            border-top: 1px solid var(--border);
            font-size: 0.825rem;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="brand-icon">🍃</div>
                <div>
                    <h1>Havo Monitoringi</h1>
                    <p>Bot Foydalanuvchilari Admin Paneli</p>
                </div>
            </div>
            <div class="header-actions">
                <a href="/admin/api/users" target="_blank" class="btn">
                    <span>📄 JSON format</span>
                </a>
                <button onclick="location.reload()" class="btn btn-primary">
                    <span>🔄 Yangilash</span>
                </button>
            </div>
        </header>

        <!-- Stat kartochkalari -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-title">Jami Foydalanuvchilar <span>👥</span></div>
                <div class="stat-value">{total_users}</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Faol Bot Foydalanuvchilari <span>🟢</span></div>
                <div class="stat-value" style="color: #34d399;">{active_users}</div>
            </div>
            <div class="stat-card alert-card">
                <div class="stat-title">Xavfli Havo Xabarlari <span>🚨</span></div>
                <div class="stat-value" style="color: #f87171;">{alert_users}</div>
            </div>
            <div class="stat-card digest-card">
                <div class="stat-title">Ertalabki Xabarnoma <span>☀️</span></div>
                <div class="stat-value" style="color: #38bdf8;">{digest_users}</div>
            </div>
            <div class="stat-card" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(56, 189, 248, 0.25);">
                <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                    <span style="font-size: 1.35rem;">🌍</span>
                    <div>
                        <div style="font-size: 0.725rem; color: #94a3b8; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">Top Global Shaharlar</div>
                        <div style="font-size: 0.9rem; font-weight: 600; color: #f8fafc; margin-top: 3px; display: flex; flex-wrap: wrap; gap: 4px;">{top_cities_html}</div>
                    </div>
                </div>
                <div style="font-size: 0.8rem; color: #38bdf8; background: rgba(6, 182, 212, 0.15); border: 1px solid rgba(6, 182, 212, 0.3); padding: 4px 12px; border-radius: 9999px;">
                    Joylashuv tanlaganlar: <b>{with_loc_users}</b> / {total_users}
                </div>
            </div>
        </div>

        <!-- Qidiruv va Filterlar -->
        <div class="controls-card">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="searchInput" placeholder="Telegram ID, hudud yoki mintaqa bo'yicha qidirish..." oninput="filterRows()">
            </div>
            <div class="filters">
                <select id="statusFilter" class="filter-select" onchange="filterRows()">
                    <option value="all">Holat: Barchasi</option>
                    <option value="active">🟢 Faol</option>
                    <option value="inactive">🔴 Bloklagan</option>
                </select>
                <select id="langFilter" class="filter-select" onchange="filterRows()">
                    <option value="all">Til: Barchasi</option>
                    <option value="uz">🇺🇿 O'zbekcha</option>
                    <option value="ru">🇷🇺 Русский</option>
                    <option value="en">🇬🇧 English</option>
                </select>
            </div>
        </div>

        <!-- Jadval -->
        <div class="table-card">
            <div class="table-responsive">
                <table id="usersTable">
                    <thead>
                        <tr>
                            <th style="width: 40px;">#</th>
                            <th>Telegram ID</th>
                            <th>Til</th>
                            <th>Joriy Shahar</th>
                            <th>Uy Manzili</th>
                            <th>Saqlangan Joylar</th>
                            <th>Vaqt Mintaqasi</th>
                            <th>Xabarnomalar</th>
                            <th>Holat</th>
                            <th>Qo'shilgan sana</th>
                        </tr>
                    </thead>
                    <tbody id="usersBody">
                        {table_rows}
                    </tbody>
                </table>
            </div>
            <div class="table-footer">
                <div>Ko'rsatilmoqda: <b id="visibleCount">{total_users}</b> ta foydalanuvchi</div>
                <div>Oxirgi yangilanish: {datetime.now(tz).strftime("%H:%M:%S")}</div>
            </div>
        </div>
    </div>

    <script>
        function filterRows() {{
            const search = document.getElementById('searchInput').value.toLowerCase().trim();
            const status = document.getElementById('statusFilter').value;
            const lang = document.getElementById('langFilter').value;
            const rows = document.querySelectorAll('#usersBody tr[data-search]');

            let visibleCount = 0;
            rows.forEach(row => {{
                const rowSearch = row.getAttribute('data-search') || '';
                const rowStatus = row.getAttribute('data-status') || '';
                const rowLang = row.getAttribute('data-lang') || '';

                const matchesSearch = !search || rowSearch.includes(search);
                const matchesStatus = status === 'all' || rowStatus === status;
                const matchesLang = lang === 'all' || rowLang === lang;

                if (matchesSearch && matchesStatus && matchesLang) {{
                    row.style.display = '';
                    visibleCount++;
                }} else {{
                    row.style.display = 'none';
                }}
            }});
            document.getElementById('visibleCount').textContent = visibleCount;
        }}
    </script>
</body>
</html>
"""


@admin_router.get("", response_class=HTMLResponse)
@admin_router.get("/", response_class=HTMLResponse)
@admin_router.get("/users", response_class=HTMLResponse)
async def admin_users_page(request: Request) -> HTMLResponse:
    """Admin panel: Foydalanuvchilar ro'yxati va statistikasi HTML sahifasi."""
    settings = get_settings()
    async with get_session_factory()() as session:
        users = (
            await session.scalars(
                select(User)
                .options(selectinload(User.saved_locations))
                .order_by(User.id.desc())
            )
        ).all()

    content = _render_admin_html(list(users), settings.tz)
    return HTMLResponse(content=content)


@admin_router.get("/api/users")
async def admin_users_json(request: Request) -> JSONResponse:
    """Foydalanuvchilar ma'lumotlarini JSON formatida olish."""
    settings = get_settings()
    async with get_session_factory()() as session:
        users = (
            await session.scalars(
                select(User)
                .options(selectinload(User.saved_locations))
                .order_by(User.id.desc())
            )
        ).all()

    data = [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "language": u.language,
            "is_active": u.is_active,
            "alert_enabled": u.alert_enabled,
            "daily_digest": u.daily_digest,
            "digest_time": u.digest_time,
            "timezone": u.timezone,
            "district": u.district.name_uz if u.district else None,
            "district_country": u.district.country if u.district else None,
            "home_district": u.home_district.name_uz if u.home_district else None,
            "home_district_country": u.home_district.country if u.home_district else None,
            "saved_locations": [
                {
                    "district_id": loc.district_id,
                    "name": loc.district.name_uz if loc.district else "",
                    "country": loc.district.country if loc.district else "",
                    "is_home": loc.is_home,
                }
                for loc in (getattr(u, "saved_locations", []) or [])
            ],
            "created_at": _format_dt(u.created_at, settings.tz),
        }
        for u in users
    ]
    return JSONResponse(
        {
            "total": len(data),
            "active": sum(1 for u in users if u.is_active),
            "users": data,
        }
    )
