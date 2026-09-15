from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts, notion_client as nc
from bot.config import ADMIN_USER_IDS

router = Router()


def decision_keyboard(page_id: str, candidate_telegram_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.ADMIN_TAKE_BTN, callback_data=f"decide:take:{page_id}:{candidate_telegram_id}")
    b.button(text=texts.ADMIN_RESERVE_BTN, callback_data=f"decide:reserve:{page_id}:{candidate_telegram_id}")
    b.button(text=texts.ADMIN_REJECT_BTN, callback_data=f"decide:reject:{page_id}:{candidate_telegram_id}")
    b.adjust(3)
    return b.as_markup()


DECISION_LABELS = {"take": "Берём", "reserve": "В резерв", "reject": "Не берём"}


@router.callback_query(lambda c: c.data and c.data.startswith("decide:"))
async def on_decision(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_USER_IDS:
        await callback.answer(texts.ADMIN_NOT_AUTHORIZED, show_alert=True)
        return

    _, action, page_id, candidate_id = callback.data.split(":")
    decision = DECISION_LABELS[action]

    admin_name = callback.from_user.full_name
    await nc.record_decision(page_id, decision, admin_name)

    # убираем кнопки, показываем итог
    await callback.message.edit_reply_markup(reply_markup=None)
    new_caption = (callback.message.caption or callback.message.text or "") + (
        f"\n\nРешение: {decision} ({admin_name})"
    )
    try:
        if callback.message.video:
            await callback.message.edit_caption(caption=new_caption)
        else:
            await callback.message.edit_text(new_caption)
    except Exception:
        pass

    await callback.answer(texts.ADMIN_DECISION_RECORDED.format(decision=decision))

    # Пишем кандидату ТОЛЬКО если взяли. В остальных случаях — полная тишина.
    if action == "take":
        await callback.bot.send_message(int(candidate_id), texts.ACCEPTED_MESSAGE)
