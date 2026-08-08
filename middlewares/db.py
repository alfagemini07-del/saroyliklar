from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable
from database import AsyncSessionLocal, User
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

class DbMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            
            user_telegram_id = None
            if event.message:
                user_telegram_id = event.message.from_user.id
            elif event.callback_query:
                user_telegram_id = event.callback_query.from_user.id

            if user_telegram_id:
                try:
                    result = await session.execute(select(User).where(User.telegram_id == user_telegram_id))
                    db_user = result.scalar_one_or_none()
                    
                    if db_user and db_user.is_blocked:
                        text = "⛔️ <b>Sizning profilingiz admin tomonidan bloklangan.</b>\n\nBotdan foydalana olmaysiz."
                        if event.message:
                            await event.message.answer(text, parse_mode="HTML")
                        elif event.callback_query:
                            await event.callback_query.answer("Siz bloklangansiz!", show_alert=True)
                        return
                except Exception as e:
                    logger.error(f"User blok tekshiruvida xato: {e}")

            result = await handler(event, data)
            return result