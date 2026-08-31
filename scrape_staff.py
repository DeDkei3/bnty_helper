import requests
from bs4 import BeautifulSoup

# сюда добавляем ссылки на страницы других кафедр по мере того,
# как находим их — просто новая строка в списке
STAFF_URLS = [
    "https://bntu.by/departments/ipf/staff",
]


def fetch_staff(url):
    headers = {
        # без этого некоторые сайты блокируют запросы, не похожие на браузер
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def parse_staff(html):
    soup = BeautifulSoup(html, "html.parser")
    people = []

    # ищем все ссылки вида mailto: — это надёжный якорь,
    # у каждого сотрудника на странице есть ровно одна такая ссылка
    mail_links = soup.select('a[href^="mailto:"]')

    print(f"Найдено ссылок mailto: {len(mail_links)}")

    for mail_link in mail_links:
        email = mail_link["href"].replace("mailto:", "").split("?")[0]

        # поднимаемся вверх по дереву HTML до "карточки" сотрудника —
        # обычно это ближайший общий родительский блок
        card = mail_link.find_parent(["div", "article", "li"])
        if not card:
            continue

        # телефон — соседняя ссылка tel: внутри той же карточки
        tel_link = card.select_one('a[href^="tel:"]')
        phone = tel_link["href"].replace("tel:", "").strip() if tel_link else None

        # фото — первая картинка в карточке (если есть)
        img = card.select_one("img")
        photo_url = None
        if img and img.get("src"):
            photo_url = img["src"]
            if photo_url.startswith("/"):
                photo_url = "https://bntu.by" + photo_url

        # имя и должность — берём весь текст карточки и печатаем,
        # чтобы разобраться, как их вычленить в твоём случае
        text_preview = card.get_text(" ", strip=True)[:200]

        people.append({
            "email": email,
            "phone": phone,
            "photo_url": photo_url,
            "text_preview": text_preview,
        })

    return people


def debug_ancestors(html):
    """Диагностика: смотрим, на каком уровне родительского тега
    находится имя и должность сотрудника (для первой карточки)."""
    soup = BeautifulSoup(html, "html.parser")
    first_mail = soup.select_one('a[href^="mailto:"]')
    if not first_mail:
        print("Не нашли ни одной mailto-ссылки вообще")
        return

    node = first_mail
    for level in range(1, 8):
        node = node.parent
        if node is None:
            break
        tag_info = f"<{node.name} class='{node.get('class')}'>"
        text = node.get_text(" ", strip=True)[:250]
        print(f"--- уровень {level}: {tag_info} ---")
        print(text)
        print()


def find_card(mail_link):
    """Поднимаемся от mailto-ссылки до карточки сотрудника целиком
    (div с классом, содержащим 'Full', например 'deanFull')."""
    return mail_link.find_parent(
        lambda tag: tag.name == "div" and tag.get("class") and
        any("Full" in c for c in tag.get("class"))
    )


def extract_role(role_div):
    """Из блока вида '<звание> <a>кафедра</a> <a>факультет</a>'
    достаём звание отдельно и список ссылок (кафедра/факультет) отдельно."""
    title_parts = []
    links = []
    for child in role_div.children:
        if getattr(child, "name", None) == "a":
            links.append(child.get_text(strip=True))
        elif isinstance(child, str):
            text = child.strip()
            if text:
                title_parts.append(text)
    return " ".join(title_parts).strip(), links


def parse_staff(html):
    soup = BeautifulSoup(html, "html.parser")
    mail_links = soup.select('a[href^="mailto:"]')
    people = []

    for mail_link in mail_links:
        card = find_card(mail_link)
        if not card:
            continue

        email = mail_link["href"].replace("mailto:", "").split("?")[0]

        tel_link = card.select_one('a[href^="tel:"]')
        phone = tel_link["href"].replace("tel:", "").strip() if tel_link else None

        name_div = card.select_one(".deanLastName")
        name_parts = name_div.get_text().split() if name_div else []
        # обычно [Фамилия, Имя, Отчество], но бывают двойные имена/фамилии —
        # на всякий случай не падаем, если частей не ровно 3
        last_name = name_parts[0] if len(name_parts) > 0 else None
        first_name = name_parts[1] if len(name_parts) > 1 else None
        patronymic = " ".join(name_parts[2:]) if len(name_parts) > 2 else None

        role_divs = card.select(".deanRole")
        admin_role = None
        academic_title = None
        department = None
        if len(role_divs) == 2:
            admin_title, admin_links = extract_role(role_divs[0])
            admin_role = " ".join([admin_title] + admin_links).strip()
            academic_title, links = extract_role(role_divs[1])
            department = links[0] if links else None
        elif len(role_divs) == 1:
            academic_title, links = extract_role(role_divs[0])
            department = links[0] if links else None

        people.append({
            "last_name": last_name,
            "first_name": first_name,
            "patronymic": patronymic,
            "full_name": " ".join(p for p in [last_name, first_name, patronymic] if p),
            "admin_role": admin_role,
            "academic_title": academic_title,
            "department": department,
            "email": email,
            "phone": phone,
        })

    return people


def fetch_all_staff():
    """Проходит по всем кафедрам из STAFF_URLS и собирает всех сотрудников
    в один список."""
    all_people = []
    for url in STAFF_URLS:
        print(f"Загружаю {url} ...")
        html = fetch_staff(url)
        people = parse_staff(html)
        print(f"  найдено сотрудников: {len(people)}")
        all_people.extend(people)
    return all_people


if __name__ == "__main__":
    people = fetch_all_staff()
    print(f"\nВсего сотрудников по всем кафедрам: {len(people)}\n")
    for p in people[:6]:
        print(p)
        print("---")