"""Yengil rejim uchun Redis o'rnini bosuvchi xotiradagi kesh.

Faqat ilova ishlatadigan metodlar bor: get, set(ex=), ping, aclose. Jarayon qayta ishga tushsa
kesh tozalanadi; bu muhim emas, chunki ma'lumot bazadan yoki provayderdan qayta olinadi.
"""

import time
from collections.abc import Callable
from functools import lru_cache


class MemoryCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._data: dict[str, tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and self._clock() >= expires_at:
            del self._data[key]
            return None
        return value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = (value, self._clock() + ex if ex else None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        """Umumiy nusxa yopilmaydi: uni bot ham, fon vazifalari ham ishlatadi."""


@lru_cache
def get_memory_cache() -> MemoryCache:
    """Bir jarayon ichida hamma (bot, API, jadval) bitta keshdan foydalanadi."""
    return MemoryCache()
