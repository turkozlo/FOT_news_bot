import logging
import re
import asyncio
import json
import csv
from pathlib import Path
from typing import List
from telethon import TelegramClient, events

# --- Импортируем модуль обработки ---
from newsendingbot.offer_generator import generate_offer_async
from newsendingbot.process_logging import log_news_process
from newsendingbot.deduplicator import Deduplicator

# --- НАСТРОЙКИ ---
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.json"

def load_config():
    # Используем utf-8-sig для обработки возможного BOM
    with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
        return json.load(f)

cfg = load_config()
API_ID = int(cfg['api_id']) if str(cfg.get('api_id', '')).isdigit() else 0
API_HASH = cfg.get('api_hash', '*****')
BOT_TOKEN = cfg.get('bot_token', '*****')

# Глобальный семафор для ограничения одновременных запросов к LLM
llm_semaphore = asyncio.Semaphore(1)

# -- Дедубликатор --
deduplicator = Deduplicator(
    threshold=0.85,
    news_file="INN_Experiment/queue_for_distribution_recommendations.json" # Используем локальный файл INN_Experiment
)

# --- ЗАГРУЗКА ДАННЫХ КОМПАНИЙ (INN Experiment) ---
COMPANY_DB = {}

def normalize_name(name: str) -> str:
    """
    Удаляет кавычки, юр. префиксы и лишние пробелы для поиска.
    Позволяет найти 'Ромашка' в тексте 'Компания «Ромашка»'.
    """
    if not name:
        return ""
    n = name.lower()
    # Удаляем кавычки всех видов
    n = re.sub(r"['\"«»]", "", n)
    # Удаляем частые префиксы (осторожно, чтобы не удалить часть названия)
    n = re.sub(r"\b(ооо|ао|пао|зао|ип)\b", "", n)
    # Удаляем лишние пробелы и знаки препинания (кроме букв и цифр)
    n = re.sub(r"[^\w\d\s-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def load_company_data():
    global COMPANY_DB
    COMPANY_DB = {} # Сброс при перезагрузке
    try:
        csv_path = Path("INN_Experiment/company_data.csv")
        if not csv_path.exists():
             return
             
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Сохраняем по "чистому" имени
                clean_key = normalize_name(row["name"])
                if clean_key:
                    COMPANY_DB[clean_key] = row
    except Exception as e:
        print(f"[INN Experiment] Ошибка загрузки CSV: {e}")

load_company_data()

def search_company_data(text: str):
    """
    Ищет упоминание компании в тексте новости.
    Возвращает СПИСОК найденных записей (list of dict).
    """
    # Нормализуем текст новости так же, как имена компаний
    t_norm = normalize_name(text)
    
    found_companies = []
    
    for clean_name, data in COMPANY_DB.items():
        # Ищем чистое имя в чистом тексте
        if clean_name in t_norm:
             found_companies.append(data)
             
    return found_companies

# Маппинг суффиксов месяцев на русские названия
MONTH_NAMES = {
    "jan": "Янв", "feb": "Фев", "mar": "Мар", "apr": "Апр",
    "may": "Май", "jun": "Июн", "jul": "Июл", "aug": "Авг",
    "sep": "Сен", "oct": "Окт", "nov": "Ноя", "dec": "Дек",
}
# Порядок для сортировки
MONTH_ORDER = ["sep", "oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug"]

def detect_months(company_row: dict) -> list:
    """
    Определяет, какие месяцы есть в строке CSV.
    Ищет ключи вида 'share_pay_XXX' и извлекает суффиксы.
    """
    months = []
    for key in company_row.keys():
        if key.startswith("share_pay_"):
            suffix = key.replace("share_pay_", "")
            if suffix in MONTH_NAMES:
                months.append(suffix)
    # Сортируем по порядку
    months.sort(key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99)
    return months

def build_company_context(company_info: dict) -> str:
    """
    Формирует компактный текстовый блок с данными о компании для LLM.
    Автоматически определяет месяцы из CSV-колонок.
    """
    months = detect_months(company_info)
    
    context = f"══════════════════════════════\n"
    context += f"Компания: {company_info['name']}\n"
    context += f"ИНН: {company_info['inn']}\n\n"
    
    # Компактная таблица по месяцам
    context += "Помесячная статистика:\n"
    
    shares = []
    for m in months:
        label = MONTH_NAMES.get(m, m)
        e_pay = company_info.get(f"empl_pay_{m}", "?")
        e_nopay = company_info.get(f"empl_nopay_{m}", "?")
        share = company_info.get(f"share_pay_{m}", "?")
        avg_sal = company_info.get(f"avg_sal_{m}", "?")
        
        try:
            total = int(e_pay) + int(e_nopay)
        except:
            total = "?"
        
        context += f"  {label}: {e_pay} с ФОТ из {total}, доля={share}, ср.ЗП={avg_sal}\n"
        
        try:
            shares.append(float(share))
        except:
            pass
    
    # Тренд за весь период
    if len(shares) >= 2:
        first = shares[0]
        last = shares[-1]
        delta = round(last - first, 2)
        first_month = MONTH_NAMES.get(months[0], months[0])
        last_month = MONTH_NAMES.get(months[-1], months[-1])
        
        if delta < 0:
            trend = f"СНИЖЕНИЕ на {abs(delta)} за период ({first_month}: {first} → {last_month}: {last})"
        elif delta > 0:
            trend = f"РОСТ на {delta} за период ({first_month}: {first} → {last_month}: {last})"
        else:
            trend = f"СТАБИЛЬНО ({first})"
        
        context += f"\nТРЕНД ДОЛИ ФОТ: {trend}\n"
    
    context += f"══════════════════════════════\n\n"
    return context


# --- Промты для пользователей ---
SYSTEM_PROMPT = """
Ты — старший аналитик корпоративного блока банка.
Твоя задача — на основе текста новости и (если есть) внутренних данных о клиенте подготовить аналитическую рекомендацию для менеджера.

═══════════════════════════════════════
ФОРМАТ ВЫВОДА (КРИТИЧЕСКИ ВАЖНО)
═══════════════════════════════════════
- Пиши ТОЛЬКО простой текст с HTML-тегами (<b>жирный</b>).
- НИКОГДА не используй markdown: НЕ пиши ```html```, ````, **, ##, - [ ] и т.п.
- Это сообщение будет отправлено в Telegram, где markdown-разметка отображается как мусор.

═══════════════════════════════════════
ЭТАП 1: ФИЛЬТРАЦИЯ (применяй ВСЕГДА)
═══════════════════════════════════════

ПРАВИЛО 1 (Название):
Нет конкретного названия компании/имени предпринимателя → Ссылка на источник: ссылка + «Нет предложений»

ПРАВИЛО 2 (Масштаб):
Инвестиции < 10 млн руб. или рабочих мест <= 3 → «Нет предложений».
Исключение: крупные объекты (завод, ТЦ, фабрика) даже без точных цифр.

ПРАВИЛО 3 (Регион):
Целевые: Хабаровский, Приморский, Сахалинская, ЕАО, Амурская, Чукотский, Камчатский, Магаданская.
Не из списка → «Нет предложений». Не определён → укажи: "Регион не указан, необходимо проверить."

ПРАВИЛО 4 (Смена руководства):
→ «Встретиться с новым руководителем для обсуждения сотрудничества».

ПРАВИЛО 5 (Игнорировать): Общие новости без компаний, самозанятые, с/х (кроме нового крупного предприятия).

═══════════════════════════════════════
ЭТАП 2: ФОРМИРОВАНИЕ ОТВЕТА
═══════════════════════════════════════

ТВОЯ СПЕЦИАЛИЗАЦИЯ — ТОЛЬКО ЗАРПЛАТНЫЙ ПРОЕКТ (ФОТ):
- Подключение ЗП-проекта
- Увеличение доли ФОТ
- Подключение новых сотрудников к ЗП-проекту
- Выяснение причин снижения доли ФОТ

НЕ ПРЕДЛАГАЙ другие банковские продукты (кредиты, РКО, эквайринг и т.д.) — это НЕ твоя зона.

▸ ВАРИАНТ А — Есть блок [ДАННЫЕ О КЛИЕНТЕ ИЗ БАЗЫ]:

Формат ответа:

Ссылка на источник: ссылка
Краткое описание новости (1 строка)

<b>Клиент:</b> [Название] (ИНН [число])

<b>Аналитика:</b>
КРАТКОЕ резюме (3-5 строк). НЕ перечисляй все цифры — дай ВЫВОДЫ:
- Тренд: доля ФОТ растёт/падает/стабильна, на сколько за период
- Ключевая проблема или возможность для ФОТ
- Потенциал из новости: сколько новых рабочих мест может появиться
  (если точная цифра не указана в новости — можешь ПРЕДПОЛОЖИТЬ на основе объёма инвестиций, но ОБЯЗАТЕЛЬНО пиши "по предварительной оценке" или "предположительно". Помни: далеко не все инвестиции идут на зарплаты, основная часть — оборудование, стройка и т.д.)

<b>Рекомендация:</b>
Только по теме ФОТ:
1. Повод для контакта (привязка к событию из новости)
2. Если доля ФОТ снижается — назначить встречу, выяснить причины, предложить увеличение доли
3. Если расширение/стройка — предложить ЗП-проект для новых сотрудников
4. Если доля ФОТ растёт — закрепить результат, предложить расширение

▸ ВАРИАНТ Б — Блока [ДАННЫЕ О КЛИЕНТЕ ИЗ БАЗЫ] НЕТ:

Ссылка на источник: ссылка
Краткое описание новости (1 строка)

<b>Рекомендация:</b>
Краткое предложение по ФОТ (подключить ЗП-проект / выйти с предложением и т.д.)

═══════════════════════════════════════
ВАЖНО
═══════════════════════════════════════
- ВСЕГДА указывай ИНН если есть в данных
- НЕ ПРИДУМЫВАЙ конкретные цифры (суммы кредитов, процентные ставки, точное число сотрудников), если их нет в новости или данных
- НЕ предлагай продукты вне темы ФОТ
- Пиши для загруженного менеджера — кратко, по делу, с выводами
- ТОЛЬКО HTML-теги, НИКАКОГО markdown
    """

# Каналы, которые отслеживаем
CHANNELS = {
    '@businessnews27',
    '@RGSNIK27',
}

# --- Маппинг регион -> список user_id ---
REGION_USERS = {
    "Хабаровский край": [],
    "Приморский край": [],
    "Сахалинская область": [],
    "Еврейская автономная область": [],
    "Амурская область": [],
    "Чукотский автономный округ": [],
    "Камчатский край": [],
    "Магаданская область": [],
}

# --- Список "других" регионов ---
OTHER_REGIONS_LIST = [
    "Республика Адыгея", "Майкоп",
    "Республика Башкортостан", "Уфа",
    "Республика Бурятия", "Улан-Удэ",
    "Республика Алтай", "Горно-Алтайск",
    "Республика Дагестан", "Махачкала",
    "Республика Ингушетия", "Магас",
    "Кабардино-Балкарская Республика", "Нальчик",
    "Республика Калмыкия", "Элиста",
    "Республика Карачаево-Черкесия", "Черкесск",
    "Республика Карелия", "Петрозаводск",
    "Республика Коми", "Сыктывкар",
    "Республика Марий Эл", "Йошкар-Ола",
    "Республика Мордовия", "Саранск",
    "Республика Саха (Якутия)", "Якутск",
    "Республика Северная Осетия-Алания", "Владикавказ",
    "Республика Татарстан", "Казань",
    "Республика Тыва", "Кызыл",
    "Удмуртская Республика", "Ижевск",
    "Республика Хакасия", "Абакан",
    "Чеченская Республика", "Грозный",
    "Чувашская Республика", "Чебоксары",
    "Алтайский край", "Барнаул",
    "Краснодарский край", "Краснодар",
    "Красноярский край", "Красноярск",
    "Ставропольский край", "Ставрополь",
    "Архангельская область", "Архангельск",
    "Астраханская область", "Астрахань",
    "Белгородская область", "Белгород",
    "Брянская область", "Брянск",
    "Владимирская область", "Владимир",
    "Волгоградская область", "Волгоград",
    "Вологодская область", "Вологда",
    "Воронежская область", "Воронеж",
    "Ивановская область", "Иваново",
    "Иркутская область", "Иркутск",
    "Калининградская область", "Калининград",
    "Калужская область", "Калуга",
    "Кемеровская область", "Кемерово",
    "Кировская область", "Киров",
    "Костромская область", "Кострома",
    "Курганская область", "Курган",
    "Курская область", "Курск",
    "Ленинградская область", "Санкт-Петербург",
    "Липецкая область", "Липецк",
    "Московская область", "Москва",
    "Мурманская область", "Мурманск",
    "Нижегородская область", "Нижний Новгород",
    "Новгородская область", "Великий Новгород",
    "Новосибирская область", "Новосибирск",
    "Омская область", "Омск",
    "Оренбургская область", "Оренбург",
    "Орловская область", "Орел",
    "Пензенская область", "Пенза",
    "Пермский край", "Пермь",
    "Псковская область", "Псков",
    "Ростовская область", "Ростов-на-Дону",
    "Рязанская область", "Рязань",
    "Самарская область", "Самара",
    "Саратовская область", "Саратов",
    "Свердловская область", "Екатеринбург",
    "Smolenskaya oblast", "Smolensk",
    "Тамбовская область", "Тамбов",
    "Тверская область", "Тверь",
    "Томская область", "Томск",
    "Тульская область", "Тула",
    "Тюменская область", "Тюмень",
    "Ульяновская область", "Ульяновск",
    "Челябинская область", "Челябинск",
    "Забайкальский край", "Чита",
    "Ярославская область", "Ярославль",
    "г. Москва", "г. Санкт-Петербург",
    "Ненецкий автономный округ", "Нарьян-Мар",
    "Ханты-Мансийский автономный округ - Югра", "Ханты-Мансийск",
    "Ямало-Ненецкий автономный округ", "Салехард"
]

def build_flexible_other_regions_pattern(regions_list):
    roots = set()
    for name in regions_list:
        n = name.lower().strip()
        n = re.sub(r"\b(респ\.?|республика|обл\.?|область|край|ао|автономный|г\.?|город)\b", "", n)
        n = re.sub(r"[^а-яё\- ]", " ", n)
        n = n.strip()
        if not n:
            continue
        for part in n.split():
            if len(part) > 4:
                roots.add(re.escape(part[:6]))
            else:
                roots.add(re.escape(part))
    alternation = "|".join(sorted(roots, key=lambda x: -len(x)))
    pattern = rf"\b(?:{alternation})[а-яё\-]{{0,5}}\b"
    return re.compile(pattern, flags=re.IGNORECASE)

OTHER_REGIONS_PATTERN = build_flexible_other_regions_pattern(OTHER_REGIONS_LIST)

def detect_other_regions(text: str):
    if not text:
        return []
    found = set()
    for m in OTHER_REGIONS_PATTERN.finditer(text):
        found.add(m.group(0))
    return list(found)

def detect_regions(text: str) -> List[str]:
    if not text:
        return []
    regions_found = set()
    t = text.lower()
    patterns = {
        "Хабаровский край": r"\b(?:хабаровск(?:\w{0,7})|хабаровск(?:\w{0,7})?\s*кра(?:\w{0,4})|комсомольск(?:\w{0,7})?[-\s]?на[-\s]?амуре|николаевск(?:\w{0,7})?[-\s]?на[-\s]?амуре|советск(?:\w{0,7})\sгаван(?:\w{0,7}))\b",
        "Приморский край": r"\b(?:приморск(?:ий|\w{0,7})?|приморь(?:е|\w{0,7})?|владивосток(?:\w{0,7})|уссурийск(?:\w{0,7})|находк(?:\w{0,7})?|арсеньев(?:\w{0,7})|артем(?:\w{0,7})|лесозаводск(?:\w{0,7}))\b",
        "Сахалинская область": r"\b(?:сахалин(?:\w{0,7})|южно[-\s]?сахалинск(?:\w{0,7})|корсаков(?:\w{0,7})|холмск(?:\w{0,7})|остров(?:а\s+курильск(?:ие|их))?)\b",
        "Еврейская автономная область": r"\b(?:евре(?:йск(?:\w{0,7})?\s+автономн(?:\w{0,7})?(?:\s+область|)|еврейская\s+ао)|биробиджан(?:\w{0,7})|облучье(?:\w{0,7})|EАО)\b",
        "Амурская область": r"\b(?:амурск(?:ая|ой|ую|ом|\w{0,5})?|благовещенск(?:\w{0,7})|свободный(?:\w{0,7})|тында(?:\w{0,7})|зея(?:\w{0,7})|шимановск(?:\w{0,7}))\b",
        "Чукотский автономный округ": r"\b(?:чукотск(?:\w{0,7})?|чукотка(?:\w{0,7})|анадыр(?:ь|е|я)?|певек(?:\w{0,7})|беринговск(?:\w{0,7}))\b",
        "Камчатский край": r"\b(?:камчатск(?:\w{0,7})?|петропавловск[-\s]?камчатск(?:\w{0,7})?|елизово(?:\w{0,7})|магаданск(?:\w{0,7})?)\b",
        "Магаданская область": r"\b(?:магадан(?:\w{0,7})|магаданск(?:\w{0,7})?|сеяха(?:\w{0,7}))\b"
    }
    for region, pat in patterns.items():
        try:
            regex = re.compile(pat, flags=re.IGNORECASE | re.VERBOSE)
            if regex.search(t):
                regions_found.add(region)
        except re.error:
            if region.lower().split()[0] in t:
                regions_found.add(region)
    return list(regions_found)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация клиента Telethon
SESSION_NAME = str(Path(__file__).resolve().parent / "inn_experiment_session")
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handle_new_message(event):
    try:
        if not event.is_channel:
            return
            
        sender = await event.get_chat()
        channel_username = getattr(sender, 'username', None)
        channel_key = f"@{channel_username}" if channel_username else None
        
        if channel_key and channel_key not in CHANNELS:
            return

        message = event.message
        if not (message.text or message.caption):
            return

        original_text = message.text or message.caption

        # --- Разбиваем пачку на отдельные новости ---
        news_blocks = [
            block.strip()
            for block in original_text.split("──────────")
            if block.strip()
        ]  

        recommendations_by_user = {}

        for news in news_blocks:
            regions = detect_regions(news) 
            other_regions = detect_other_regions(news)

            if not regions and other_regions:
                # Пропускаем, если есть только прочие регионы
                continue

            if regions:
                target_user_ids = set()
                for r in regions:
                    ulist = REGION_USERS.get(r, [])
                    for uid in ulist:
                        target_user_ids.add(uid)
            else:
                target_user_ids = set(uid for ulist in REGION_USERS.values() for uid in ulist)

            actual_recipients = []
            final_proposal = None

            async def process_user_task(uid):
                try:
                    if deduplicator.is_duplicate(news, user_id=uid):
                        return None
                    
                    found_companies = search_company_data(news)
                    final_system_prompt = SYSTEM_PROMPT
                    final_news_text = news

                    if found_companies:
                        inn_context = "\n\n[ДАННЫЕ О КЛИЕНТЕ ИЗ БАЗЫ]\n"
                        for company_info in found_companies:
                            inn_context += build_company_context(company_info)
                        final_news_text += inn_context

                    async with llm_semaphore:
                        offer = await generate_offer_async(final_news_text, final_system_prompt)
                        await asyncio.sleep(1.5)
                        
                        if offer:
                            # Чистим markdown
                            offer = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', offer)
                            offer = re.sub(r'\*(.+?)\*', r'<b>\1</b>', offer)
                            offer = re.sub(r'```\w*\n?', '', offer)
                            offer = re.sub(r'^#{1,3}\s+', '', offer, flags=re.MULTILINE)
                        
                        return (uid, offer)
                except Exception as e:
                    logger.error(f"Ошибка обработки task для user {uid}: {e}")
                    return None

            tasks = [process_user_task(uid) for uid in target_user_ids]
            results = await asyncio.gather(*tasks)

            for res in results:
                if not res: continue
                uid, processed_text = res
                if not processed_text: continue

                if "Нет предложений" not in processed_text:
                    recommendations_by_user.setdefault(uid, []).append(processed_text)
                    final_proposal = processed_text
                    actual_recipients.append(uid)
                    deduplicator.add(news, user_id=uid)

            if actual_recipients and final_proposal:
                region_str = ", ".join(regions) if regions else "Не определен"
                try:
                    log_news_process(news, final_proposal, region_str, actual_recipients)
                except Exception as e:
                    logger.error(f"Ошибка логирования: {e}")

        for user_id, recs in recommendations_by_user.items():
            for rec in recs:
                try:
                    await client.send_message(user_id, rec, parse_mode='html')
                    logger.info(f"Сообщение отправлено пользователю {user_id}")
                except Exception as e:
                    logger.exception(f"Ошибка отправки пользователю {user_id}: {e}")

    except Exception as e:
        logger.exception("Ошибка при обработке сообщения")

async def main():
    logger.info("INN Experiment Bot (Telethon) запускается...")
    await client.start(bot_token=BOT_TOKEN)
    logger.info("Бот на связи!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
