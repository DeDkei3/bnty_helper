import re
import datetime
import xlrd

SHEET_NAME = "ИПФ 2 КУРС"
GROUP_NUMBER = 10903625

DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
DAY_INDEX = {name: i for i, name in enumerate(DAYS)}  # понедельник=0 ... суббота=5

SEMESTER_START = datetime.date(2026, 9, 1)
SEMESTER_END = datetime.date(2026, 12, 28)

LESSON_TYPES = {
    "лекционное занятие": "лекция",
    "практическое занятие": "практика",
    "лабораторное занятие": "лабораторная",
    "лабораторно занятие": "лабораторная",
    "курсовой проект": "курсовой проект",
}


def parse_time(time_str):
    """'8.00 - 8.45  8.50 - 9.35' -> ('08:00', '09:35')"""
    nums = re.findall(r"\d{1,2}[.:]\d{2}", time_str)
    if len(nums) < 2:
        return None, None
    start = nums[0].replace(".", ":")
    end = nums[-1].replace(".", ":")
    # приводим к формату HH:MM
    def pad(t):
        h, m = t.split(":")
        return f"{int(h):02d}:{m}"
    return pad(start), pad(end)


def split_into_sub_lessons(lines):
    """Одна пара может содержать 1 или 2 вложенных занятия
    (если неделя чётная/нечётная — разные предметы).
    Разбиваем список строк на группы по маркеру типа занятия."""
    groups = []
    current = []
    for line in lines:
        is_type_marker = any(t in line.lower() for t in LESSON_TYPES) or line.strip().startswith("(")
        if is_type_marker and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


TEACHER_TITLE_PATTERN = (
    r"(доц\.|ст\.\s*пр\.|ст\.\s*преп\.|пр\.|проф\.|асс\.|ассистент)\s*"
    r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?"
)


def parse_sub_lesson(lines):
    """Достаём тип, неделю, предмет, преподавателя и аудиторию
    из ВСЕГО текста пары сразу (не завязываемся на то, в какой
    именно строке что лежит — общие лекции пишут всё одной строкой,
    обычные пары — размазывают по нескольким)."""
    if not lines:
        return None

    full_text = " ".join(lines)
    full_text = re.sub(r"\s+", " ", full_text).strip()

    lesson_type = None
    for key, val in LESSON_TYPES.items():
        if key in full_text.lower():
            lesson_type = val
            break

    week_parity = "both"
    week_match = re.search(r"([12])\s*нед", full_text)
    if week_match:
        week_parity = week_match.group(1)

    # убираем маркеры типа занятия и недели — это "шум" для дальнейшего разбора
    text = re.sub(r"\([^)]*\)", "", full_text)
    text = re.sub(r"[12]\s*нед\.?", "", text)

    # аудитория: строчная "а" + номер + "к" + номер
    room_match = re.search(r"а\.?\s*\d+[а-я]?\s*к\.?\s*\d+[а-я]?", text)
    if not room_match:
        # в исходнике иногда пропущена буква "а" перед номером (опечатка) —
        # ищем просто "номер + к + номер"
        room_match = re.search(r"\b\d{2,4}\s*к\.?\s*\d+[а-я]?", text)
    room = room_match.group(0) if room_match else None
    if room:
        text = text.replace(room, "")

    # преподаватель: звание + Фамилия + инициалы
    teacher_match = re.search(TEACHER_TITLE_PATTERN, text)
    teacher = teacher_match.group(0) if teacher_match else None
    if teacher:
        text = text.replace(teacher, "")

    subject = text.strip(" .,")
    subject = re.sub(r"\s+", " ", subject)

    return {
        "type": lesson_type,
        "week_parity": week_parity,
        "subject": subject if subject else None,
        "teacher": teacher,
        "room": room,
    }


def looks_like_new_lesson(lines):
    """Похоже ли начало блока на начало НОВОЙ пары, а не продолжение
    предыдущей. Считаем новой, если есть маркер типа занятия, скобка,
    упоминание преподавателя или аудитории — а не просто "довесок"
    вроде адреса организации при производственном обучении."""
    if not lines:
        return False
    text = " ".join(lines).strip()
    if text.startswith("("):
        return True
    if any(t in text.lower() for t in LESSON_TYPES):
        return True
    if re.search(TEACHER_TITLE_PATTERN, text):
        return True
    if re.search(r"а\.?\s*\d+[а-я]?\s*к\.?\s*\d+[а-я]?", text):
        return True
    return False


def merge_continuations(all_lessons):
    """Если у слота нет признаков новой пары — считаем его
    продолжением предыдущего слота того же дня (пара растянута
    на несколько временных ячеек, например 'производственное обучение')."""
    merged = []
    for lesson in all_lessons:
        if (
            merged
            and merged[-1]["day"] == lesson["day"]
            and not looks_like_new_lesson(lesson["raw_lines"])
        ):
            merged[-1]["raw_lines"].extend(lesson["raw_lines"])
            merged[-1]["time_end_override"] = lesson["time"]
        else:
            lesson["time_end_override"] = None
            merged.append(lesson)
    return merged


def dates_for_day(day_name, week_parity):
    """Все реальные даты в семестре для дня недели day_name,
    с учётом чётности недели (или все, если week_parity='both')."""
    target_weekday = DAY_INDEX[day_name]
    dates = []
    d = SEMESTER_START
    # первая неделя семестра = неделя 1 (нечётная)
    first_monday = SEMESTER_START - datetime.timedelta(days=SEMESTER_START.weekday())
    while d <= SEMESTER_END:
        if d.weekday() == target_weekday:
            weeks_since_start = (d - first_monday).days // 7
            this_parity = "1" if weeks_since_start % 2 == 0 else "2"
            if week_parity == "both" or week_parity == this_parity:
                dates.append(d)
        d += datetime.timedelta(days=1)
    return dates


def find_group_columns(sheet):
    """Находит диапазон колонок (start, end) для нужной группы,
    ищем строку, где встречается номер группы, и следующий номер группы
    после неё (граница блока)."""
    for r in range(sheet.nrows):
        row_vals = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        for c, val in enumerate(row_vals):
            if val == GROUP_NUMBER:
                # ищем следующую непустую "номер группы" ячейку правее
                next_group_col = sheet.ncols
                for c2 in range(c + 1, sheet.ncols):
                    v2 = row_vals[c2]
                    if isinstance(v2, float) and v2 > 1000000:
                        next_group_col = c2
                        break
                return c, next_group_col
    raise ValueError("Группа не найдена на листе")


def find_day_start_rows(sheet):
    """Возвращает список (day_name, start_row) для каждого дня недели."""
    result = []
    for r in range(sheet.nrows):
        val = sheet.cell_value(r, 0)
        if isinstance(val, str) and val.strip().lower() in DAYS:
            result.append((val.strip().lower(), r))
    return result


def extract_block_text(sheet, row_start, row_end, col_start, col_end):
    """Собирает непустые строки текста из прямоугольного блока ячеек
    в колонках нашей группы. Если там пусто — значит это общая пара
    для нескольких групп сразу, и текст записан ЛЕВЕЕ (ищем ближайшую
    непустую ячейку от col_start до начала таблицы)."""
    lines = []
    for r in range(row_start, row_end):
        for c in range(col_start, col_end):
            if r >= sheet.nrows or c >= sheet.ncols:
                continue
            val = sheet.cell_value(r, c)
            if isinstance(val, float):
                val = str(int(val)) if val == int(val) else str(val)
            val = str(val).strip()
            if val:
                lines.append(val)

    if lines:
        return lines

    # ничего своего — ищем общую (межгрупповую) пару левее
    for r in range(row_start, row_end):
        for c in range(col_start - 1, 1, -1):  # идём влево до колонки 2
            val = sheet.cell_value(r, c)
            if isinstance(val, float):
                val = str(int(val)) if val == int(val) else str(val)
            val = str(val).strip()
            if val:
                return [val]
    return []


def get_time_slot_rows(day_start_row):
    """5 временных слотов, каждый через 4 строки от начала дня."""
    return [day_start_row + i * 4 for i in range(5)]


def main():
    wb = xlrd.open_workbook("2 курс 2026 осень.xls")
    sheet = wb.sheet_by_name(SHEET_NAME)

    col_start, col_end = find_group_columns(sheet)
    print(f"Колонки для группы {GROUP_NUMBER}: {col_start}-{col_end}")

    days = find_day_start_rows(sheet)
    print(f"Найдены дни: {days}")

    all_lessons = []

    for day_name, day_row in days:
        slot_rows = get_time_slot_rows(day_row)
        for i, slot_row in enumerate(slot_rows):
            time_val = sheet.cell_value(slot_row, 1)
            next_slot_row = slot_rows[i + 1] if i + 1 < len(slot_rows) else slot_row + 4
            block_lines = extract_block_text(
                sheet, slot_row, next_slot_row, col_start, col_end
            )
            if block_lines:
                all_lessons.append({
                    "day": day_name,
                    "time": time_val,
                    "raw_lines": block_lines,
                })

    print(f"\nНайдено занятых слотов: {len(all_lessons)}\n")

    all_lessons = merge_continuations(all_lessons)
    print(f"После слияния растянутых пар: {len(all_lessons)}\n")

    final_lessons = []
    for lesson in all_lessons:
        time_start, time_end = parse_time(lesson["time"])
        if lesson.get("time_end_override"):
            _, extended_end = parse_time(lesson["time_end_override"])
            if extended_end:
                time_end = extended_end
        sub_groups = split_into_sub_lessons(lesson["raw_lines"])
        for sub in sub_groups:
            parsed = parse_sub_lesson(sub)
            if not parsed or not parsed["subject"]:
                continue
            lesson_dates = dates_for_day(lesson["day"], parsed["week_parity"])
            for d in lesson_dates:
                final_lessons.append({
                    "date": d,
                    "day": lesson["day"],
                    "time_start": time_start,
                    "time_end": time_end,
                    "subject": parsed["subject"],
                    "type": parsed["type"],
                    "teacher": parsed["teacher"],
                    "room": parsed["room"],
                })

    final_lessons.sort(key=lambda x: (x["date"], x["time_start"]))

    print(f"Итого записей с реальными датами за семестр: {len(final_lessons)}\n")
    print("Первые 15 занятий:")
    for l in final_lessons[:15]:
        print(f"{l['date']} ({l['day']}) {l['time_start']}-{l['time_end']} | "
              f"{l['type']} | {l['subject']} | {l['teacher']} | {l['room']}")

    return final_lessons


if __name__ == "__main__":
    main()