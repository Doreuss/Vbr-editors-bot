import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.handlers import start, test_task, admin
from bot.scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)


async def _health(request):
    return web.Response(text="VBR Editors Bot is running")


async def _run_health_server():
    """Render (free Web Service tier) checks that the process has an open
    HTTP port to consider it alive. The bot itself has nothing to do with
    HTTP - this just satisfies that health check alongside the real bot."""
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin.router)
    dp.include_router(test_task.router)
    dp.include_router(start.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    await _run_health_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
