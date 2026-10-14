"""Yengil rejimda fon vazifalari (Celery o'rniga): asyncio vazifasini ishga tushirib, xatosini yozadi."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger(__name__)

# Vazifaga havola saqlanmasa, asyncio uni tugamasdan o'chirib yuborishi mumkin
_running: set[asyncio.Task] = set()


async def _guard(coro: Coroutine[Any, Any, Any], name: str) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Fon vazifasi xato bilan tugadi: %s", name)


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task:
    task = asyncio.create_task(_guard(coro, name), name=name)
    _running.add(task)
    task.add_done_callback(_running.discard)
    return task
