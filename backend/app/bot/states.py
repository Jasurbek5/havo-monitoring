from aiogram.fsm.state import State, StatesGroup


class ComplaintForm(StatesGroup):
    """Murojaat yuborish qadamlari."""

    category = State()
    photo = State()
    location = State()
    text = State()
    confirm = State()


class LocationSearchForm(StatesGroup):
    """Shahar yoki tuman qidirish holati."""

    waiting_for_query = State()
