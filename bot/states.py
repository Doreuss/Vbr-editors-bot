from aiogram.fsm.state import StatesGroup, State


class Ankета(StatesGroup):
    name = State()
    city = State()
    almaty_office = State()
    capcut_experience = State()
    portfolio = State()
    weekly_time = State()
    contact = State()


class TestTask(StatesGroup):
    waiting_for_submission = State()
    waiting_for_confirmation = State()
