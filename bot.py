import datetime
import logging
import threading
import time
import sys
import os

import pytz
import telebot
from telebot.types import Message, CallbackQuery

import config
from database import Database
from schedule_service import ScheduleService
import keyboards

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("RaspBot")

# Инициализация сервисов
db = Database(config.DB_PATH)
schedule_service = ScheduleService(config.GROUP_CODE)

# Если токен не задан, используем заглушку, чтобы декораторы не падали при импорте
active_token = config.BOT_TOKEN if (config.BOT_TOKEN and ":" in config.BOT_TOKEN) else "123456789:ABCdef_DUMMY_TOKEN_FOR_INIT"
bot = telebot.TeleBot(active_token, parse_mode="HTML")

try:
    LOCAL_TZ = pytz.timezone(config.TIMEZONE_NAME)
except Exception:
    LOCAL_TZ = pytz.timezone("Europe/Simferopol")


def get_now() -> datetime.datetime:
    """Возвращает текущую дату и время с учетом локального часового пояса (МСК)."""
    return datetime.datetime.now(LOCAL_TZ)


def safe_delete_message(chat_id: int, message_id: int):
    """Безопасное удаление сообщения (без падения при ошибке)."""
    if not message_id:
        return
    try:
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}")


def send_clean_schedule_message(chat_id: int, offset_days: int = 0) -> int:
    """
    Удаляет старое сообщение бота (если оно было) и отправляет свежее расписание.
    Возвращает id нового отправленного сообщения.
    """
    user = db.get_user(chat_id)
    subgroup = user.get("subgroup", 0) if user else 0
    old_msg_id = user.get("last_message_id") if user else None

    # Удаляем старое сообщение бота
    if old_msg_id:
        safe_delete_message(chat_id, old_msg_id)

    # Формируем расписание
    target_date = get_now().date() + datetime.timedelta(days=offset_days)
    if offset_days == 0:
        prefix = "Сегодня"
    elif offset_days == 1:
        prefix = "Завтра"
    elif offset_days == -1:
        prefix = "Вчера"
    else:
        prefix = target_date.strftime("%d.%m.%Y")

    text = schedule_service.format_day_schedule(target_date, subgroup, title_prefix=f"Расписание на {prefix}:")
    markup = keyboards.get_schedule_keyboard(offset_days, subgroup)

    sent_msg = bot.send_message(chat_id, text, reply_markup=markup)

    # Сохраняем новый message_id
    today_str = get_now().strftime("%Y-%m-%d")
    db.set_last_message_id(chat_id, sent_msg.message_id, sent_date=today_str)
    return sent_msg.message_id


# ============================================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================================

@bot.message_handler(commands=["start"])
def cmd_start(message: Message):
    chat_id = message.chat.id
    db.register_or_update_user(chat_id)

    # Удаляем команду пользователя для идеальной чистоты чата
    safe_delete_message(chat_id, message.message_id)

    # Отправляем чистое расписание
    send_clean_schedule_message(chat_id, offset_days=0)


@bot.message_handler(commands=["today"])
def cmd_today(message: Message):
    chat_id = message.chat.id
    safe_delete_message(chat_id, message.message_id)
    send_clean_schedule_message(chat_id, offset_days=0)


@bot.message_handler(commands=["tomorrow"])
def cmd_tomorrow(message: Message):
    chat_id = message.chat.id
    safe_delete_message(chat_id, message.message_id)
    send_clean_schedule_message(chat_id, offset_days=1)


@bot.message_handler(commands=["week"])
def cmd_week(message: Message):
    chat_id = message.chat.id
    safe_delete_message(chat_id, message.message_id)

    user = db.get_user(chat_id)
    subgroup = user.get("subgroup", 0) if user else 0
    old_msg_id = user.get("last_message_id") if user else None

    if old_msg_id:
        safe_delete_message(chat_id, old_msg_id)

    text = schedule_service.format_week_overview(get_now().date(), subgroup)
    markup = keyboards.get_week_keyboard(subgroup)
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup)

    db.set_last_message_id(chat_id, sent_msg.message_id)


@bot.message_handler(commands=["subgroup"])
def cmd_subgroup(message: Message):
    chat_id = message.chat.id
    safe_delete_message(chat_id, message.message_id)

    user = db.get_user(chat_id)
    subgroup = user.get("subgroup", 0) if user else 0
    old_msg_id = user.get("last_message_id") if user else None

    if old_msg_id:
        safe_delete_message(chat_id, old_msg_id)

    text = (
        "👥 <b>Выбор подгруппы</b>\n\n"
        "Выберите вашу подгруппу, чтобы скрыть лишние пары и лабораторные работы:"
    )
    markup = keyboards.get_subgroup_keyboard(subgroup)
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup)
    db.set_last_message_id(chat_id, sent_msg.message_id)


@bot.message_handler(commands=["settings"])
def cmd_settings(message: Message):
    chat_id = message.chat.id
    safe_delete_message(chat_id, message.message_id)

    user = db.get_user(chat_id)
    auto_notify = bool(user.get("auto_notify", 1)) if user else True
    current_time = user.get("notify_time", "07:00") if user else "07:00"
    old_msg_id = user.get("last_message_id") if user else None

    if old_msg_id:
        safe_delete_message(chat_id, old_msg_id)

    text = (
        "⚙️ <b>Настройки утренней рассылки</b>\n\n"
        f"Статус рассылки: <b>{'Включена' if auto_notify else 'Отключена'}</b>\n"
        f"Время отправки: <b>{current_time} (МСК)</b>\n\n"
        "Каждое утро бот будет удалять вчерашнее сообщение и присылать свежее расписание на день."
    )
    markup = keyboards.get_settings_keyboard(auto_notify, current_time)
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup)
    db.set_last_message_id(chat_id, sent_msg.message_id)


@bot.message_handler(commands=["help"])
def cmd_help(message: Message):
    chat_id = message.chat.id
    safe_delete_message(chat_id, message.message_id)

    text = (
        f"🤖 <b>Бот расписания группы {config.GROUP_CODE}</b>\n\n"
        "<b>Как это работает:</b>\n"
        "• Бот держит в чате ровно <b>одно актуальное сообщение</b>, удаляя старое.\n"
        "• Каждое утро (по умолчанию в 07:00 МСК) старое расписание заменяется на новое.\n"
        "• В кнопках под сообщением можно листать дни, смотреть всю неделю и выбирать подгруппу.\n\n"
        "<b>Команды:</b>\n"
        "/start — Запустить бота и получить расписание\n"
        "/today — Расписание на сегодня\n"
        "/tomorrow — Расписание на завтра\n"
        "/week — Обзор всей недели\n"
        "/subgroup — Выбрать подгруппу (1, 2 или Все)\n"
        "/settings — Настройки утренней рассылки\n"
        "/help — Эта справка"
    )
    user = db.get_user(chat_id)
    old_msg_id = user.get("last_message_id") if user else None
    if old_msg_id:
        safe_delete_message(chat_id, old_msg_id)

    markup = keyboards.get_schedule_keyboard(0, user.get("subgroup", 0) if user else 0)
    sent_msg = bot.send_message(chat_id, text, reply_markup=markup)
    db.set_last_message_id(chat_id, sent_msg.message_id)


# ============================================================================
# ОБРАБОТЧИКИ НАЖАТИЙ НА КНОПКИ (CALLBACK QUERIES)
# ============================================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: CallbackQuery):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    user = db.get_user(chat_id)
    subgroup = user.get("subgroup", 0) if user else 0

    try:
        if data.startswith("day:"):
            offset = int(data.split(":")[1])
            target_date = get_now().date() + datetime.timedelta(days=offset)
            if offset == 0:
                prefix = "Сегодня"
            elif offset == 1:
                prefix = "Завтра"
            elif offset == -1:
                prefix = "Вчера"
            else:
                prefix = target_date.strftime("%d.%m.%Y")

            text = schedule_service.format_day_schedule(target_date, subgroup, title_prefix=f"Расписание на {prefix}:")
            markup = keyboards.get_schedule_keyboard(offset, subgroup)

            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)

        elif data.startswith("week:"):
            text = schedule_service.format_week_overview(get_now().date(), subgroup)
            markup = keyboards.get_week_keyboard(subgroup)
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)

        elif data.startswith("refresh:"):
            offset = int(data.split(":")[1])
            schedule_service.fetch_index(force=True)
            schedule_service.fetch_group_schedule(force=True)

            target_date = get_now().date() + datetime.timedelta(days=offset)
            prefix = "Сегодня" if offset == 0 else ("Завтра" if offset == 1 else target_date.strftime("%d.%m.%Y"))
            text = schedule_service.format_day_schedule(target_date, subgroup, title_prefix=f"Расписание на {prefix}:")
            markup = keyboards.get_schedule_keyboard(offset, subgroup)

            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            except Exception:
                pass
            bot.answer_callback_query(call.id, text="Расписание обновлено с сайта КФУ!")

        elif data == "menu:subgroup":
            text = (
                "👥 <b>Выбор подгруппы</b>\n\n"
                "Выберите вашу подгруппу:"
            )
            markup = keyboards.get_subgroup_keyboard(subgroup)
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)

        elif data.startswith("set_subgroup:"):
            new_subgroup = int(data.split(":")[1])
            db.set_subgroup(chat_id, new_subgroup)

            target_date = get_now().date()
            text = schedule_service.format_day_schedule(target_date, new_subgroup, title_prefix="Расписание на Сегодня:")
            markup = keyboards.get_schedule_keyboard(0, new_subgroup)
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id, text=f"Подгруппа сохранена: {new_subgroup if new_subgroup > 0 else 'Все'}")

        elif data == "menu:settings":
            auto_notify = bool(user.get("auto_notify", 1)) if user else True
            current_time = user.get("notify_time", "07:00") if user else "07:00"

            text = (
                "⚙️ <b>Настройки утренней рассылки</b>\n\n"
                f"Статус рассылки: <b>{'Включена' if auto_notify else 'Отключена'}</b>\n"
                f"Время отправки: <b>{current_time} (МСК)</b>\n\n"
                "Каждое утро бот будет удалять вчерашнее сообщение и присылать свежее расписание на день."
            )
            markup = keyboards.get_settings_keyboard(auto_notify, current_time)
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)

        elif data == "toggle_notify":
            current_status = bool(user.get("auto_notify", 1)) if user else True
            new_status = not current_status
            db.set_auto_notify(chat_id, new_status)

            user = db.get_user(chat_id)
            current_time = user.get("notify_time", "07:00") if user else "07:00"

            text = (
                "⚙️ <b>Настройки утренней рассылки</b>\n\n"
                f"Статус рассылки: <b>{'Включена' if new_status else 'Отключена'}</b>\n"
                f"Время отправки: <b>{current_time} (МСК)</b>\n\n"
                "Каждое утро бот будет удалять вчерашнее сообщение и присылать свежее расписание на день."
            )
            markup = keyboards.get_settings_keyboard(new_status, current_time)
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id, text="Настройки обновлены!")

        elif data.startswith("set_time:"):
            new_time = data.split(":")[1] + ":" + data.split(":")[2]
            db.set_notify_time(chat_id, new_time)

            user = db.get_user(chat_id)
            auto_notify = bool(user.get("auto_notify", 1)) if user else True

            text = (
                "⚙️ <b>Настройки утренней рассылки</b>\n\n"
                f"Статус рассылки: <b>{'Включена' if auto_notify else 'Отключена'}</b>\n"
                f"Время отправки: <b>{new_time} (МСК)</b>\n\n"
                "Каждое утро бот будет удалять вчерашнее сообщение и присылать свежее расписание на день."
            )
            markup = keyboards.get_settings_keyboard(auto_notify, new_time)
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            bot.answer_callback_query(call.id, text=f"Время установлено: {new_time}")

    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e).lower():
            bot.answer_callback_query(call.id)
        else:
            logger.error(f"Telegram API Exception: {e}")
            bot.answer_callback_query(call.id, text="Произошла ошибка при обновлении")
    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        bot.answer_callback_query(call.id)


# ============================================================================
# ФОНОВЫЙ ПОТОК: УТРЕННЯЯ РАССЫЛКА
# ============================================================================

def morning_dispatcher_loop():
    """
    Фоновый цикл: проверяет каждую минуту пользователей, которым пора отправить расписание.
    Удаляет их старое сообщение и присылает свежее на сегодня.
    """
    logger.info("Фоновый диспетчер утренней рассылки запущен.")
    while True:
        try:
            now_dt = get_now()
            current_time_str = now_dt.strftime("%H:%M")
            current_date_str = now_dt.strftime("%Y-%m-%d")

            # Выбираем пользователей, у которых наступило время рассылки
            users_to_notify = db.get_users_for_morning_dispatch(current_time_str, current_date_str)

            if users_to_notify:
                logger.info(f"[{current_time_str}] Отправка утреннего расписания для {len(users_to_notify)} пользователей...")

                # Обновляем кэш расписания перед рассылкой
                schedule_service.fetch_index(force=True)
                schedule_service.fetch_group_schedule(force=True)

                for u in users_to_notify:
                    chat_id = u["chat_id"]
                    subgroup = u.get("subgroup", 0)
                    old_msg_id = u.get("last_message_id")

                    try:
                        # Удаляем вчерашнее сообщение
                        if old_msg_id:
                            safe_delete_message(chat_id, old_msg_id)

                        # Отправляем сегодняшнее
                        today_date = now_dt.date()
                        text = schedule_service.format_day_schedule(today_date, subgroup, title_prefix="Расписание на Сегодня:")
                        markup = keyboards.get_schedule_keyboard(0, subgroup)
                        sent_msg = bot.send_message(chat_id, text, reply_markup=markup)

                        # Фиксируем отправку
                        db.set_last_message_id(chat_id, sent_msg.message_id, sent_date=current_date_str)
                    except telebot.apihelper.ApiTelegramException as te:
                        # Если бот заблокирован пользователем
                        if "bot was blocked by the user" in str(te).lower() or "user is deactivated" in str(te).lower():
                            logger.warning(f"Пользователь {chat_id} заблокировал бота. Отключаем рассылку.")
                            db.set_auto_notify(chat_id, False)
                        else:
                            logger.error(f"Ошибка отправки пользователю {chat_id}: {te}")
                    except Exception as e:
                        logger.error(f"Непредвиденная ошибка отправки для {chat_id}: {e}")

                    # Небольшая пауза для избежания лимитов Telegram (30 сообщений/сек)
                    time.sleep(0.05)

        except Exception as e:
            logger.error(f"Ошибка в цикле утренней рассылки: {e}")

        # Проверяем каждые 25 секунд
        time.sleep(25)


from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "service": "RaspBot", "health": "alive"}')

    def log_message(self, format, *args):
        # Отключаем лишний лог запросов
        return


def run_health_server():
    """Запускает простой HTTP-сервер для health-check на бесплатных облачных хостингах (Render, Koyeb и др.)."""
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health-check веб-сервер слушает порт {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Health-check сервер не запущен на порту {port}: {e}")


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

def main():
    if not config.BOT_TOKEN or ":" not in config.BOT_TOKEN or "DUMMY" in config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("=" * 60)
        print("ВНИМАНИЕ! Не указан токен бота (BOT_TOKEN)!")
        print("1. Получите токен у @BotFather в Telegram.")
        print("2. Вставьте его в файл '.env' (BOT_TOKEN=...) или 'token.txt'.")
        print("=" * 60)
        return

    logger.info(f"Запуск бота для группы: {config.GROUP_CODE}...")

    # Запуск фонового health-check сервера (нужен для Render и других PaaS)
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Запуск фонового диспетчера утренней рассылки
    dispatcher_thread = threading.Thread(target=morning_dispatcher_loop, daemon=True)
    dispatcher_thread.start()

    # Запуск поллинга с авто-переподключением
    while True:
        try:
            logger.info("Бот успешно запущен и слушает сообщения (polling)...")
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            logger.error(f"Сбой polling: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)


if __name__ == "__main__":
    main()
