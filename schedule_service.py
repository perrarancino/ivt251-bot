import datetime
import urllib.request
import urllib.parse
import json
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

CFUV_API_BASE = "https://cfuv.ru/wp-json/cfu/v1/sched/"
DEFAULT_GROUP = "ИВТ-б-о-251"

# Стандартные звонки КФУ (на случай сбоя API)
DEFAULT_BELLS = {
    1: ("08:00", "09:30"),
    2: ("09:50", "11:20"),
    3: ("11:30", "13:00"),
    4: ("13:20", "14:50"),
    5: ("15:00", "16:30"),
    6: ("16:40", "18:10"),
    7: ("18:20", "19:50"),
    8: ("20:00", "21:30"),
}

DAYS_NAMES = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
    7: "Воскресенье",
}


def http_get_json(url: str, timeout: int = 15) -> Optional[Any]:
    """Делает GET-запрос с User-Agent и возвращает распарсенный JSON."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except Exception as e:
        logger.error(f"Ошибка запроса к {url}: {e}")
        return None


class ScheduleService:
    def __init__(self, group_code: str = DEFAULT_GROUP):
        self.group_code = group_code
        self.cached_index: Optional[Dict[str, Any]] = None
        self.cached_group: Optional[Dict[str, Any]] = None
        self.last_index_fetch: Optional[datetime.datetime] = None
        self.last_group_fetch: Optional[datetime.datetime] = None
        self.cache_ttl = datetime.timedelta(minutes=30)

    def fetch_index(self, force: bool = False) -> Optional[Dict[str, Any]]:
        now = datetime.datetime.now()
        if not force and self.cached_index and self.last_index_fetch:
            if now - self.last_index_fetch < self.cache_ttl:
                return self.cached_index

        url = f"{CFUV_API_BASE}index"
        data = http_get_json(url)
        if data and isinstance(data, dict):
            self.cached_index = data
            self.last_index_fetch = now
            return data
        return self.cached_index

    def fetch_group_schedule(self, force: bool = False) -> Optional[Dict[str, Any]]:
        now = datetime.datetime.now()
        if not force and self.cached_group and self.last_group_fetch:
            if now - self.last_group_fetch < self.cache_ttl:
                return self.cached_group

        encoded_code = urllib.parse.quote(self.group_code)
        url = f"{CFUV_API_BASE}group?code={encoded_code}"
        data = http_get_json(url)
        if data and isinstance(data, dict):
            self.cached_group = data
            self.last_group_fetch = now
            return data
        return self.cached_group

    def get_bells_dict(self) -> Dict[int, Tuple[str, str]]:
        """Возвращает словарь {номер_пары: (время_начала, время_конца)}."""
        index = self.fetch_index()
        bells_dict = dict(DEFAULT_BELLS)
        if index and "bells" in index and isinstance(index["bells"], list):
            for b in index["bells"]:
                p_num = b.get("пара")
                start = b.get("начало")
                end = b.get("конец")
                if p_num and start and end:
                    bells_dict[int(p_num)] = (start, end)
        return bells_dict

    def get_week_parity(self, target_date: datetime.date) -> str:
        """Определяет чётность недели для указанной даты: 'чёт' или 'нечёт'."""
        index = self.fetch_index()
        monday = target_date - datetime.timedelta(days=target_date.weekday())
        monday_str = monday.strftime("%Y-%m-%d")

        if index and "weeks" in index:
            weeks = index["weeks"]
            ch_weeks = weeks.get("ch", [])
            nch_weeks = weeks.get("nch", [])

            if monday_str in ch_weeks:
                return "чёт"
            if monday_str in nch_weeks:
                return "нечёт"

            # Если дата вне списка, смотрим на базовый понедельник
            all_known = [(w, "чёт") for w in ch_weeks] + [(w, "нечёт") for w in nch_weeks]
            if all_known:
                all_known.sort(key=lambda x: x[0])
                ref_date = datetime.datetime.strptime(all_known[-1][0], "%Y-%m-%d").date()
                ref_parity = all_known[-1][1]
                diff_weeks = (monday - ref_date).days // 7
                if diff_weeks % 2 == 0:
                    return ref_parity
                else:
                    return "нечёт" if ref_parity == "чёт" else "чёт"

        # Если данные из index не получены, проверяем поле now
        if index and "now" in index and isinstance(index["now"], dict):
            now_parity = index["now"].get("parity")
            if now_parity in ("чёт", "нечёт"):
                return now_parity

        # Дефолтный fallback по номеру недели в году
        week_num = target_date.isocalendar()[1]
        return "чёт" if week_num % 2 == 0 else "нечёт"

    def get_lessons_for_day(
        self,
        target_date: datetime.date,
        subgroup_filter: int = 0
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Возвращает (parity, lessons_list).
        subgroup_filter: 0 - все, 1 - 1-я подгруппа, 2 - 2-я подгруппа
        """
        parity = self.get_week_parity(target_date)
        day_of_week = target_date.isoweekday()  # 1..7 (Пн..Вс)

        group_data = self.fetch_group_schedule()
        if not group_data or "занятия" not in group_data:
            return parity, []

        all_lessons = group_data["занятия"]
        filtered = []

        for item in all_lessons:
            # Проверка дня недели
            if item.get("день") != day_of_week:
                continue

            # Проверка чётности
            item_parity = item.get("чётность")
            if item_parity != "обе" and item_parity != parity:
                continue

            # Фильтр по подгруппе (если подгруппа 0 у предмета - она для всех)
            item_subgroup = item.get("подгруппа", 0)
            if subgroup_filter > 0 and item_subgroup != 0 and item_subgroup != subgroup_filter:
                continue

            filtered.append(item)

        # Сортировка по номеру пары и подгруппе
        filtered.sort(key=lambda x: (x.get("пара", 0), x.get("подгруппа", 0)))
        return parity, filtered

    def format_day_schedule(
        self,
        target_date: datetime.date,
        subgroup_filter: int = 0,
        title_prefix: str = "Расписание на"
    ) -> str:
        """Форматирует расписание на день в красивый Markdown-текст для Telegram."""
        parity, lessons = self.get_lessons_for_day(target_date, subgroup_filter)
        day_num = target_date.isoweekday()
        day_name = DAYS_NAMES.get(day_num, "")
        date_str = target_date.strftime("%d.%m.%Y")
        bells = self.get_bells_dict()

        parity_display = "Чётная" if parity == "чёт" else "Нечётная"
        subgroup_str = f" | Подгруппа {subgroup_filter}" if subgroup_filter > 0 else " | Все подгруппы"

        header = (
            f"📅 <b>{title_prefix} {day_name} ({date_str})</b>\n"
            f"🔔 Неделя: <b>{parity_display}</b> | Группа: <code>{self.group_code}</code>{subgroup_str}\n"
            f"───────────────────\n"
        )

        if not lessons:
            if day_num == 7:
                body = "\n🎉 <b>Воскресенье — выходной день! Пар нет.</b> Отдыхаем! 🏖️\n"
            else:
                body = "\n🌴 <b>На этот день занятий нет!</b>\n"
            return header + body

        num_emojis = {
            1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
            5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
        }

        # Группируем пары по их номеру
        from collections import defaultdict
        lessons_by_para = defaultdict(list)
        for l in lessons:
            lessons_by_para[l.get("пара", 0)].append(l)

        body_lines = []
        for p_num in sorted(lessons_by_para.keys()):
            items = lessons_by_para[p_num]
            bell_time = bells.get(p_num, ("??:??", "??:??"))
            time_str = f"{bell_time[0]} – {bell_time[1]}"
            emoji = num_emojis.get(p_num, f"[{p_num}]")

            body_lines.append(f"\n{emoji} <b>{p_num} пара</b> (<code>{time_str}</code>)")

            for it in items:
                subject = it.get("предмет") or "Без названия"
                kind = it.get("вид") or ""
                kind_str = f" [{kind}]" if kind else ""
                subgroup = it.get("подгруппа", 0)
                sub_badge = f" <i>(п/г {subgroup})</i>" if subgroup > 0 else ""

                body_lines.append(f"📚 <b>{subject}</b>{kind_str}{sub_badge}")

                # Преподаватели
                teachers = it.get("преподаватели") or []
                if teachers:
                    t_str = ", ".join(teachers)
                    body_lines.append(f"  👨‍🏫 <i>{t_str}</i>")

                # Аудитория и корпус
                aud = it.get("аудитория") or ""
                korp = it.get("корпус") or ""
                loc_parts = []
                if aud:
                    loc_parts.append(f"ауд. <b>{aud}</b>")
                if korp:
                    loc_parts.append(f"{korp}")
                if loc_parts:
                    body_lines.append(f"  📍 {', '.join(loc_parts)}")

                # Примечания / Онлайн
                notes = it.get("примечание") or ""
                online = it.get("онлайн") or ""
                if notes:
                    body_lines.append(f"  ℹ️ {notes}")
                if online:
                    body_lines.append(f"  🌐 {online}")

        footer = (
            f"\n───────────────────\n"
            f"🔄 <i>Синхронизировано с cfuv.ru</i>"
        )
        return header + "\n".join(body_lines) + footer

    def format_week_overview(self, target_date: datetime.date, subgroup_filter: int = 0) -> str:
        """Краткий обзор расписания на всю текущую неделю."""
        monday = target_date - datetime.timedelta(days=target_date.weekday())
        parity = self.get_week_parity(monday)
        parity_display = "Чётная" if parity == "чёт" else "Нечётная"

        text = (
            f"🗓 <b>Расписание на неделю ({monday.strftime('%d.%m')} – "
            f"{(monday + datetime.timedelta(days=6)).strftime('%d.%m.%Y')})</b>\n"
            f"🔔 Неделя: <b>{parity_display}</b> | Группа: <code>{self.group_code}</code>\n"
            f"───────────────────\n"
        )

        bells = self.get_bells_dict()
        has_any = False

        for i in range(6):  # Пн-Сб
            day_date = monday + datetime.timedelta(days=i)
            day_name = DAYS_NAMES.get(day_date.isoweekday(), "")
            _, day_lessons = self.get_lessons_for_day(day_date, subgroup_filter)

            if not day_lessons:
                text += f"\n<b>{day_name} ({day_date.strftime('%d.%m')}):</b>\n  <i>Занятий нет</i>\n"
                continue

            has_any = True
            text += f"\n<b>{day_name} ({day_date.strftime('%d.%m')}):</b>\n"

            # Группируем по паре
            from collections import defaultdict
            p_dict = defaultdict(list)
            for l in day_lessons:
                p_dict[l.get("пара", 0)].append(l)

            for p_num in sorted(p_dict.keys()):
                items = p_dict[p_num]
                bell_time = bells.get(p_num, ("??:??", "??:??"))
                subjs = []
                for it in items:
                    s_name = it.get("предмет") or "Дисциплина"
                    s_kind = f" ({it.get('вид')})" if it.get('вид') else ""
                    s_aud = f" [{it.get('аудитория')}]" if it.get('аудитория') else ""
                    sub_p = f" (п/г {it.get('подгруппа')})" if it.get('подгруппа') else ""
                    subjs.append(f"{s_name}{s_kind}{sub_p}{s_aud}")
                text += f"  • {p_num} пара ({bell_time[0]}): " + "; ".join(subjs) + "\n"

        if not has_any:
            text += "\n🌴 На этой неделе пар не запланировано!\n"

        text += "\n───────────────────\n🔄 <i>cfuv.ru</i>"
        return text
