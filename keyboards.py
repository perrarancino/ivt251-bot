from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_schedule_keyboard(current_offset_days: int = 0, subgroup: int = 0) -> InlineKeyboardMarkup:
    """
    Клавиатура под сообщением с расписанием:
    - перелистывание дней
    - переключение подгруппы
    - просмотр недели
    - обновление
    """
    markup = InlineKeyboardMarkup(row_width=3)

    subgroup_label = {0: "👥 Все", 1: "👥 Подгр. 1", 2: "👥 Подгр. 2"}.get(subgroup, "👥 Все")

    # Кнопки навигации по дням
    prev_offset = current_offset_days - 1
    next_offset = current_offset_days + 1

    btn_prev = InlineKeyboardButton("◀ Пред. день", callback_data=f"day:{prev_offset}")
    btn_today = InlineKeyboardButton("📅 Сегодня", callback_data="day:0")
    btn_next = InlineKeyboardButton("След. день ▶", callback_data=f"day:{next_offset}")

    btn_week = InlineKeyboardButton("🗓 Вся неделя", callback_data="week:0")
    btn_sub = InlineKeyboardButton(f"{subgroup_label}", callback_data="menu:subgroup")

    btn_refresh = InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{current_offset_days}")
    btn_settings = InlineKeyboardButton("⚙️ Настройки", callback_data="menu:settings")

    markup.add(btn_prev, btn_today, btn_next)
    markup.add(btn_week, btn_sub)
    markup.add(btn_refresh, btn_settings)

    return markup


def get_week_keyboard(subgroup: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для режима просмотра всей недели."""
    markup = InlineKeyboardMarkup(row_width=2)
    subgroup_label = {0: "👥 Все", 1: "👥 Подгр. 1", 2: "👥 Подгр. 2"}.get(subgroup, "👥 Все")

    btn_back = InlineKeyboardButton("◀ К сегодняшнему дню", callback_data="day:0")
    btn_sub = InlineKeyboardButton(f"{subgroup_label}", callback_data="menu:subgroup")
    btn_refresh = InlineKeyboardButton("🔄 Обновить", callback_data="week:0")

    markup.add(btn_back, btn_sub)
    markup.add(btn_refresh)
    return markup


def get_subgroup_keyboard(current_subgroup: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура выбора подгруппы."""
    markup = InlineKeyboardMarkup(row_width=1)

    s0_mark = " ✅" if current_subgroup == 0 else ""
    s1_mark = " ✅" if current_subgroup == 1 else ""
    s2_mark = " ✅" if current_subgroup == 2 else ""

    markup.add(
        InlineKeyboardButton(f"👥 Вся группа (все подгруппы){s0_mark}", callback_data="set_subgroup:0"),
        InlineKeyboardButton(f"👤 1-я подгруппа{s1_mark}", callback_data="set_subgroup:1"),
        InlineKeyboardButton(f"👤 2-я подгруппа{s2_mark}", callback_data="set_subgroup:2"),
        InlineKeyboardButton("◀ Назад к расписанию", callback_data="day:0")
    )
    return markup


def get_settings_keyboard(auto_notify: bool, current_time: str) -> InlineKeyboardMarkup:
    """Клавиатура настроек рассылки."""
    markup = InlineKeyboardMarkup(row_width=2)

    toggle_text = "🔔 Утренняя рассылка: ВКЛ" if auto_notify else "🔕 Утренняя рассылка: ВЫКЛ"
    markup.add(InlineKeyboardButton(toggle_text, callback_data="toggle_notify"))

    markup.add(
        InlineKeyboardButton(f"06:30{' ✅' if current_time == '06:30' else ''}", callback_data="set_time:06:30"),
        InlineKeyboardButton(f"07:00{' ✅' if current_time == '07:00' else ''}", callback_data="set_time:07:00"),
    )
    markup.add(
        InlineKeyboardButton(f"07:30{' ✅' if current_time == '07:30' else ''}", callback_data="set_time:07:30"),
        InlineKeyboardButton(f"08:00{' ✅' if current_time == '08:00' else ''}", callback_data="set_time:08:00"),
    )

    markup.add(InlineKeyboardButton("◀ Назад к расписанию", callback_data="day:0"))
    return markup
