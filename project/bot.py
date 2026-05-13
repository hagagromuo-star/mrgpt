from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from admin import router as admin_router
from config import BOT_TOKEN
from database import init_db
from user_handlers import router as user_router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to .env or Render Environment Variables.")

    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(admin_router)
    dispatcher.include_router(user_router)

    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
