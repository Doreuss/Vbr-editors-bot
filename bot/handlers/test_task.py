import re
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot import texts, notion_client as nc
from bot.states import TestTask
from bot.config import ADMIN_GROUP_ID, REVIEW_SLA_DAYS

router = Router()

TIKTOK_LINK_RE = re.compile(r"https?://\S+", re.IGNORECASE)

_candidate_counter = {"n": 0}  # простая нумерация карточек в рамках процесса


def _kb(*buttons: str):
    b = ReplyKeyboardBuilder()
    for t in buttons:
        b.button(text=t)
    b.adjust(1)
    return b.as_markup(resize_keyboard=True)


@router.message(F.text == texts.START_TEST_BTN)
async def on_start_test(message: Message, state: FSMContext):
    existing = await nc.find_candidate_by_telegram_id(message.from_user.id)
    page_id = existing["id"]
    await nc.mark_test_started(page_id)
    await state.update_data(page_id=page_id)
    await state.set_state(TestTask.waiting_for_submission)
    await message.answer(
        texts.SEND_VIDEO_OR_LINK_PROMPT,
        reply_markup=_kb(texts.SEE_TASK_AGAIN_BTN, texts.FAQ_BTN),
    )


@router.message(F.text == texts.SEND_VIDEO_BTN)
async def on_send_video_button(message: Message, state: FSMContext):
    """Кнопка показывается при возврате в бот (тест уже начат, но не отправлен).
    Раньше не имела обработчика — состояние диалога терялось, из-за чего
    следующее сообщение (видео или ссылка) бот просто не видел."""
    existing = await nc.find_candidate_by_telegram_id(message.from_user.id)
    if not existing:
        return
    await state.update_data(page_id=existing["id"])
    await state.set_state(TestTask.waiting_for_submission)
    await message.answer(
        texts.SEND_VIDEO_OR_LINK_PROMPT,
        reply_markup=_kb(texts.SEE_TASK_AGAIN_BTN, texts.FAQ_BTN),
    )


@router.message(F.text == texts.SEE_TASK_AGAIN_BTN)
async def on_see_task_again(message: Message):
    from bot.handlers.start import send_test_task
    existing = await nc.find_candidate_by_telegram_id(message.from_user.id)
    await send_test_task(message, existing["id"], show_start_button=False)


@router.message(F.text == texts.FAQ_BTN)
async def on_faq(message: Message):
    await message.answer(texts.FAQ_TEXT.format(sla=REVIEW_SLA_DAYS))


@router.message(TestTask.waiting_for_submission, F.video)
async def on_video_submission(message: Message, state: FSMContext):
    await state.update_data(
        submission_method="Файл в бота",
        submission_link=None,
        video_file_id=message.video.file_id,
    )
    await state.set_state(TestTask.waiting_for_confirmation)
    await message.answer(texts.DRAFT_RECEIVED, reply_markup=_kb(texts.CONFIRM_SEND_BTN, texts.REPLACE_VIDEO_BTN))


@router.message(TestTask.waiting_for_submission, F.text.regexp(TIKTOK_LINK_RE))
async def on_link_submission(message: Message, state: FSMContext):
    await state.update_data(
        submission_method="Ссылка TikTok",
        submission_link=message.text.strip(),
        video_file_id=None,
    )
    await state.set_state(TestTask.waiting_for_confirmation)
    await message.answer(texts.DRAFT_RECEIVED, reply_markup=_kb(texts.CONFIRM_SEND_BTN, texts.REPLACE_VIDEO_BTN))


@router.message(TestTask.waiting_for_submission)
async def on_wrong_attachment(message: Message):
    await message.answer(texts.WRONG_ATTACHMENT)


@router.message(TestTask.waiting_for_confirmation, F.text == texts.REPLACE_VIDEO_BTN)
async def on_replace(message: Message, state: FSMContext):
    await state.set_state(TestTask.waiting_for_submission)
    await message.answer(texts.SEND_VIDEO_OR_LINK_PROMPT)


@router.message(TestTask.waiting_for_confirmation, F.text == texts.CONFIRM_SEND_BTN)
async def on_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    page_id = data["page_id"]

    await nc.mark_submitted(page_id, data["submission_method"], data.get("submission_link"))
    await message.answer(texts.SUBMITTED_CONFIRMATION.format(sla=REVIEW_SLA_DAYS))
    await state.clear()

    await _post_admin_card(message, page_id, data)


async def _post_admin_card(message: Message, page_id: str, data: dict):
    from bot.handlers import admin as admin_handlers

    page = await nc.find_candidate_by_telegram_id(message.from_user.id)
    props = page["properties"]

    def _text(prop):
        arr = props.get(prop, {}).get("rich_text", [])
        return arr[0]["text"]["content"] if arr else "-"

    def _sel(prop):
        s = props.get(prop, {}).get("select")
        return s["name"] if s else "-"

    def _url(prop):
        return props.get(prop, {}).get("url") or "-"

    def _dt(prop):
        d = props.get(prop, {}).get("date")
        return d["start"] if d else None

    started_raw = _dt("Дата начала тестового")
    now = datetime.now(timezone.utc)
    if started_raw:
        started = datetime.fromisoformat(started_raw)
        duration = now - started
        duration_str = f"{int(duration.total_seconds() // 3600)} ч."
        started_str = started.strftime("%d.%m %H:%M")
    else:
        duration_str = "-"
        started_str = "-"

    _candidate_counter["n"] += 1
    text = texts.ADMIN_CARD_TEMPLATE.format(
        number=_candidate_counter["n"],
        name=_text("Имя") if _text("Имя") != "-" else message.from_user.full_name,
        city=_text("Город"),
        almaty_office=_sel("Готов в офис (Алматы)"),
        contact=f"@{message.from_user.username}" if message.from_user.username else _text("Username"),
        capcut_experience=_text("Опыт в CapCut"),
        portfolio=_url("Портфолио/TikTok"),
        source=_sel("Источник"),
        started_at=started_str,
        submitted_at=now.strftime("%d.%m %H:%M"),
        duration=duration_str,
        submission_method=data["submission_method"],
    )

    kb = admin_handlers.decision_keyboard(page_id, message.from_user.id)

    if data.get("video_file_id"):
        await message.bot.send_video(
            ADMIN_GROUP_ID, video=data["video_file_id"], caption=text, reply_markup=kb
        )
    else:
        text += f"\n\nСсылка: {data.get('submission_link')}"
        await message.bot.send_message(ADMIN_GROUP_ID, text, reply_markup=kb)
