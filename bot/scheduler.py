from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import notion_client as nc
from bot.config import NOTION_DATABASE_ID, REMINDER_AFTER_HOURS
from bot import texts


async def _check_reminders(bot: Bot):
    """Раз в час проверяет, кому пора отправить напоминание через 24ч
    после начала тестового (и кто его ещё не отправил)."""
    resp = await nc.notion.databases.query(
        database_id=NOTION_DATABASE_ID,
        filter={"property": "Статус", "select": {"equals": "Начал тестовое"}},
    )
    now = datetime.now(timezone.utc)
    for page in resp.get("results", []):
        started = page["properties"].get("Дата начала тестового", {}).get("date")
        telegram_id = page["properties"].get("Telegram ID", {}).get("rich_text")
        if not started or not telegram_id:
            continue
        started_dt = datetime.fromisoformat(started["start"])
        if now - started_dt >= timedelta(hours=REMINDER_AFTER_HOURS):
            tg_id = int(telegram_id[0]["text"]["content"])
            try:
                await bot.send_message(tg_id, texts.REMINDER_24H)
                await nc.mark_reminder_sent(page["id"])
            except Exception:
                pass  # кандидат мог заблокировать бота — не критично


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_check_reminders, "interval", hours=1, args=[bot])
    return scheduler
