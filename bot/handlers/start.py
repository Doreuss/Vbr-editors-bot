from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, ReplyKeyboardRemove

from bot import texts, notion_client as nc
from bot.states import Ankета
from bot.config import TEST_REFERENCES, TEST_SOUND_URL

router = Router()

SOURCE_BY_PAYLOAD = {
    "olx": "OLX",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "ref": "Рекомендация",
}


def _kb(*buttons: str):
    b = ReplyKeyboardBuilder()
    for t in buttons:
        b.button(text=t)
    b.adjust(1)
    return b.as_markup(resize_keyboard=True)


@router.message(CommandStart())
async def on_start(message: Message, command: CommandObject, state: FSMContext):
    telegram_id = message.from_user.id
    existing = await nc.find_candidate_by_telegram_id(telegram_id)

    if existing is None:
        source = SOURCE_BY_PAYLOAD.get((command.args or "").lower(), "Другое")
        await nc.create_candidate(
            telegram_id=telegram_id,
            username=f"@{message.from_user.username}" if message.from_user.username else "",
            source=source,
        )
        await message.answer(texts.START, reply_markup=_kb(texts.FILL_ANKETA_BTN))
        return

    status = nc.get_status(existing)
    page_id = existing["id"]

    if status in ("Открыл бота", "Начал анкету"):
        await message.answer(texts.CONTINUE_ANKETA)
        await state.update_data(page_id=page_id)
        await state.set_state(Ankета.name)
        await message.answer(texts.ANKETA_QUESTIONS[0][1])
        return

    if status in ("Заполнил анкету", "Посмотрел тестовое"):
        await send_test_task(message, page_id)
        return

    if status in ("Начал тестовое", "Получил напоминание", "Черновик получен"):
        await message.answer(
            "Ты уже начал тестовое — вот задание ещё раз.",
        )
        await send_test_task(message, page_id, show_start_button=False)
        return

    if status == "Принят" or status.startswith(("Приглашён", "Назначен", "Начал работу")):
        await message.answer(texts.ALREADY_HAVE_DATA)
        return

    if status == "Ожидает проверки":
        await message.answer(texts.UNDER_REVIEW)
        return

    if status in ("В резерве", "Не прошёл - кулдаун", "Не прошёл - можно повторно"):
        if await nc.cooldown_expired(existing):
            await message.answer(
                texts.NEW_OPPORTUNITY, reply_markup=_kb(texts.TRY_AGAIN_BTN)
            )
        else:
            await message.answer(texts.UNDER_REVIEW)
        return

    # fallback
    await message.answer(texts.UNDER_REVIEW)


@router.message(F.text == texts.TRY_AGAIN_BTN)
async def on_try_again(message: Message):
    existing = await nc.find_candidate_by_telegram_id(message.from_user.id)
    if not existing:
        return
    await nc.update_status(existing["id"], "Посмотрел тестовое")
    await send_test_task(message, existing["id"])


@router.message(F.text == texts.FILL_ANKETA_BTN)
async def start_anketa(message: Message, state: FSMContext):
    existing = await nc.find_candidate_by_telegram_id(message.from_user.id)
    await state.update_data(page_id=existing["id"])
    await nc.update_status(existing["id"], "Начал анкету")
    await state.set_state(Ankета.name)
    await message.answer(texts.ANKETA_QUESTIONS[0][1], reply_markup=ReplyKeyboardRemove())


_FIELDS = [f for f, _ in texts.ANKETA_QUESTIONS]


async def _ask_next(message: Message, state: FSMContext, current_field: str):
    idx = _FIELDS.index(current_field)
    if idx + 1 < len(_FIELDS):
        next_field, question = texts.ANKETA_QUESTIONS[idx + 1]
        await state.set_state(getattr(Ankета, next_field))
        await message.answer(question)
        return False
    return True  # анкета закончена


@router.message(Ankета.name)
async def q_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await _ask_next(message, state, "name")


@router.message(Ankета.city)
async def q_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await _ask_next(message, state, "city")


@router.message(Ankета.almaty_office)
async def q_almaty(message: Message, state: FSMContext):
    await state.update_data(almaty_office=message.text)
    await _ask_next(message, state, "almaty_office")


@router.message(Ankета.capcut_experience)
async def q_capcut(message: Message, state: FSMContext):
    await state.update_data(capcut_experience=message.text)
    await _ask_next(message, state, "capcut_experience")


@router.message(Ankета.portfolio)
async def q_portfolio(message: Message, state: FSMContext):
    await state.update_data(portfolio=message.text)
    await _ask_next(message, state, "portfolio")


@router.message(Ankета.weekly_time)
async def q_weekly(message: Message, state: FSMContext):
    await state.update_data(weekly_time=message.text)
    await _ask_next(message, state, "weekly_time")


@router.message(Ankета.contact)
async def q_contact(message: Message, state: FSMContext):
    data = await state.update_data(contact=message.text)
    await nc.save_ankета(data["page_id"], data)
    await state.clear()
    await message.answer(texts.ANKETA_DONE, reply_markup=ReplyKeyboardRemove())
    await send_test_task(message, data["page_id"])


async def send_test_task(message: Message, page_id: str, show_start_button: bool = True):
    text = texts.TEST_TASK_TEMPLATE.format(
        ref1=TEST_REFERENCES[0], ref2=TEST_REFERENCES[1], ref3=TEST_REFERENCES[2],
        sound=TEST_SOUND_URL,
    )
    kb = _kb(texts.START_TEST_BTN) if show_start_button else _kb(
        texts.SEND_VIDEO_BTN, texts.SEE_TASK_AGAIN_BTN, texts.FAQ_BTN
    )
    await message.answer(text, reply_markup=kb)
    await nc.update_status(page_id, "Посмотрел тестовое")
