import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

# TUZATILDI: Memory leak oldini olish uchun maksimal yozuvlar soni
_MAX_TIMEOUT_ENTRIES = 10_000

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 1.5):
        self.limit = limit
        self.user_timeouts: Dict[int, float] = {}

    def _cleanup_if_needed(self, now: float) -> None:
        """Dict juda katta bo'lib ketsa, eski yozuvlarni tozalaydi (Memory leak oldini olish)."""
        if len(self.user_timeouts) > _MAX_TIMEOUT_ENTRIES:
            cutoff = now - self.limit * 2
            self.user_timeouts = {
                uid: ts for uid, ts in self.user_timeouts.items()
                if ts > cutoff
            }

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Qaysi turdagi event ekanini aniqlaymiz
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            # Boshqa eventlar (InlineQuery va h.k.) uchun throttling yo'q
            return await handler(event, data)

        now = time.time()

        # TUZATILDI: Har chaqiruvda kerak bo'lsa tozalaymiz
        self._cleanup_if_needed(now)

        if user_id in self.user_timeouts:
            last_request_time = self.user_timeouts[user_id]

            # Anti-flood shart: belgilangan vaqtdan tez bossa — ignore
            if (now - last_request_time) < self.limit:
                if isinstance(event, Message):
                    await event.answer(
                        "⏳ <i>Iltimos shoshmang, tizimni ko'p marta bosa olmaysiz.</i>",
                        parse_mode="HTML"
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("Kuting...", show_alert=False)
                return

        # Vaqtni yangilab, handlerga o'tamiz
        self.user_timeouts[user_id] = now
        return await handler(event, data)
