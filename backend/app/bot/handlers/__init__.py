"""Handlerlar tartibi MUHIM.

Menyu tugmalari va /start FSM holatidan oldin ushlanishi kerak, aks holda murojaat
matni o'rniga menyu tugmasi matni saqlanib qoladi. Shuning uchun murojaat (FSM) routeri
oxirdan oldin, fallback esa eng oxirida turadi.
"""

from aiogram import Router

from app.bot.handlers import air, complaint, districts, fallback, settings, start


def get_routers() -> list[Router]:
    return [
        start.router,
        districts.router,
        air.router,
        settings.router,
        complaint.router,
        fallback.router,
    ]
