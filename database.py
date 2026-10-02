import sqlite3
import datetime
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "bot_data.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    last_message_id INTEGER DEFAULT NULL,
                    subgroup INTEGER DEFAULT 0,
                    notify_time TEXT DEFAULT '07:00',
                    auto_notify INTEGER DEFAULT 1,
                    last_sent_date TEXT DEFAULT NULL,
                    created_at TEXT
                )
            """)
            conn.commit()

    def register_or_update_user(self, chat_id: int):
        with self._get_connection() as conn:
            now = datetime.datetime.now().isoformat()
            conn.execute("""
                INSERT INTO users (chat_id, created_at)
                VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    auto_notify = 1
            """, (chat_id, now))
            conn.commit()

    def set_last_message_id(self, chat_id: int, message_id: Optional[int], sent_date: Optional[str] = None):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users
                SET last_message_id = ?,
                    last_sent_date = COALESCE(?, last_sent_date)
                WHERE chat_id = ?
            """, (message_id, sent_date, chat_id))
            conn.commit()

    def get_user(self, chat_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def set_subgroup(self, chat_id: int, subgroup: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET subgroup = ? WHERE chat_id = ?
            """, (subgroup, chat_id))
            conn.commit()

    def set_notify_time(self, chat_id: int, time_str: str):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET notify_time = ? WHERE chat_id = ?
            """, (time_str, chat_id))
            conn.commit()

    def set_auto_notify(self, chat_id: int, enabled: bool):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET auto_notify = ? WHERE chat_id = ?
            """, (1 if enabled else 0, chat_id))
            conn.commit()

    def get_users_for_morning_dispatch(self, current_time_str: str, current_date_str: str) -> List[Dict[str, Any]]:
        """
        Возвращает пользователей, которым пора отправить расписание:
        - auto_notify = 1
        - notify_time = current_time_str (например, '07:00')
        - last_sent_date != current_date_str (еще не отправляли сегодня)
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM users
                WHERE auto_notify = 1
                  AND notify_time = ?
                  AND (last_sent_date IS NULL OR last_sent_date != ?)
            """, (current_time_str, current_date_str))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_subscribers(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE auto_notify = 1")
            return [dict(row) for row in cursor.fetchall()]
