"""
Обёртка над Notion API для хранения кандидатов.

Схема базы "VBR Editors — Кандидаты" (создана заранее, см. SPEC.md):
  Имя, Telegram ID, Username, Город, Готов в офис (Алматы), Опыт в CapCut,
  Портфолио/TikTok, Загрузка в неделю, Источник, Статус,
  Дата старта анкеты, Дата начала тестового, Дата отправки тестового,
  Способ отправки, Ссылка на работу, Решение админа, Кто принял решение,
  Дата решения, Дата окончания кулдауна, Заметки
"""

from datetime import datetime, timedelta, timezone
from notion_client import AsyncClient

from bot.config import NOTION_TOKEN, NOTION_DATABASE_ID, COOLDOWN_DAYS

notion = AsyncClient(auth=NOTION_TOKEN)


def _rich_text(value: str):
    return {"rich_text": [{"text": {"content": value or ""}}]}


def _select(value: str):
    return {"select": {"name": value}} if value else {"select": None}


def _date(dt: datetime | None):
    if dt is None:
        return {"date": None}
    return {"date": {"start": dt.isoformat()}}


async def find_candidate_by_telegram_id(telegram_id: int):
    """Возвращает страницу кандидата или None, если его ещё нет в базе."""
    resp = await notion.databases.query(
        database_id=NOTION_DATABASE_ID,
        filter={"property": "Telegram ID", "rich_text": {"equals": str(telegram_id)}},
        page_size=1,
    )
    results = resp.get("results", [])
    return results[0] if results else None


async def create_candidate(telegram_id: int, username: str, source: str):
    page = await notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties={
            "Имя": {"title": [{"text": {"content": f"tg_{telegram_id}"}}]},
            "Telegram ID": _rich_text(str(telegram_id)),
            "Username": _rich_text(username or ""),
            "Источник": _select(source or "Другое"),
            "Статус": _select("Открыл бота"),
            "Дата старта анкеты": _date(datetime.now(timezone.utc)),
        },
    )
    return page


async def update_status(page_id: str, status: str):
    await notion.pages.update(
        page_id=page_id,
        properties={"Статус": _select(status)},
    )


async def save_ankета(page_id: str, data: dict):
    await notion.pages.update(
        page_id=page_id,
        properties={
            "Имя": {"title": [{"text": {"content": data["name"]}}]},
            "Город": _rich_text(data["city"]),
            "Готов в офис (Алматы)": _select(_normalize_almaty(data["almaty_office"])),
            "Опыт в CapCut": _rich_text(data["capcut_experience"]),
            "Портфолио/TikTok": {"url": data["portfolio"] if data["portfolio"] != "-" else None},
            "Загрузка в неделю": _rich_text(data["weekly_time"]),
            "Username": _rich_text(data.get("contact") or data.get("username", "")),
            "Статус": _select("Заполнил анкету"),
        },
    )


def _normalize_almaty(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if raw.startswith("да"):
        return "Да"
    if raw.startswith("нет"):
        return "Нет"
    return "Не из Алматы"


async def mark_test_started(page_id: str):
    await notion.pages.update(
        page_id=page_id,
        properties={
            "Статус": _select("Начал тестовое"),
            "Дата начала тестового": _date(datetime.now(timezone.utc)),
        },
    )


async def mark_reminder_sent(page_id: str):
    await notion.pages.update(page_id=page_id, properties={"Статус": _select("Получил напоминание")})


async def mark_submitted(page_id: str, method: str, link: str | None):
    props = {
        "Статус": _select("Ожидает проверки"),
        "Дата отправки тестового": _date(datetime.now(timezone.utc)),
        "Способ отправки": _select(method),
        "Решение админа": _select("Ожидает"),
    }
    if link:
        props["Ссылка на работу"] = {"url": link}
    await notion.pages.update(page_id=page_id, properties=props)


async def record_decision(page_id: str, decision: str, admin_name: str):
    """decision: 'Берём' | 'В резерв' | 'Не берём'"""
    status_map = {
        "Берём": "Принят",
        "В резерв": "В резерве",
        "Не берём": "Не прошёл - кулдаун",
    }
    now = datetime.now(timezone.utc)
    props = {
        "Решение админа": _select(decision),
        "Статус": _select(status_map[decision]),
        "Кто принял решение": _rich_text(admin_name),
        "Дата решения": _date(now),
    }
    if decision != "Берём":
        props["Дата окончания кулдауна"] = _date(now + timedelta(days=COOLDOWN_DAYS))
    await notion.pages.update(page_id=page_id, properties=props)


async def cooldown_expired(page) -> bool:
    cooldown = page["properties"].get("Дата окончания кулдауна", {}).get("date")
    if not cooldown:
        return False
    end = datetime.fromisoformat(cooldown["start"])
    return datetime.now(timezone.utc) >= end


def get_status(page) -> str:
    sel = page["properties"].get("Статус", {}).get("select")
    return sel["name"] if sel else ""
