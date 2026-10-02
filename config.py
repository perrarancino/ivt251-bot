import os
import sys

# Попытка прочитать .env файл вручную без сторонних тяжелых библиотек
def load_env_file(filepath=".env"):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_env_file()

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Если токен не найден в env, пробуем прочитать из файла token.txt
if not BOT_TOKEN and os.path.exists("token.txt"):
    with open("token.txt", "r", encoding="utf-8") as f:
        BOT_TOKEN = f.read().strip()

# Группа по умолчанию
GROUP_CODE = os.getenv("GROUP_CODE", "ИВТ-б-о-251").strip()

# Часовой пояс (Крым / Москва - UTC+3)
TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Simferopol").strip()

# Время утренней рассылки по умолчанию
DEFAULT_NOTIFY_TIME = os.getenv("DEFAULT_NOTIFY_TIME", "07:00").strip()

# База данных
DB_PATH = os.getenv("DB_PATH", "bot_data.db").strip()
