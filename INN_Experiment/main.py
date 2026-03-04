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
    news_file="INN_Experiment/queue_for_distribution_recommendations.json" 
)

# --- ЗАГРУЗКА ДАННЫХ КОМПАНИЙ (INN Experiment) ---
COMPANY_DB = {}

def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r"['\"«»]", "", n)
    n = re.sub(r"\b(ооо|ао|пао|зао|ип)\b", "", n)
    n = re.sub(r"[^\w\d\s-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def load_company_data():
    global COMPANY_DB
    COMPANY_DB = {} 
    try:
        csv_path = Path("INN_Experiment/company_data.csv")
        if not csv_path.exists():
             return
             
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                clean_key = normalize_name(row["name"])
                if clean_key:
                    COMPANY_DB[clean_key] = row
    except Exception as e:
        print(f"[INN Experiment] Ошибка загрузки CSV: {e}")

load_company_data()

def search_company_data(text: str):
    t_norm = normalize_name(text)
    found_companies = []
    for clean_name, data in COMPANY_DB.items():
        if clean_name in t_norm:
             found_companies.append(data)
    return found_companies

MONTH_NAMES = {
    "jan": "Янв", "feb": "Фев", "mar": "Мар", "apr": "Апр",
    "may": "Май", "jun": "Июн", "jul": "Июл", "aug": "Авг",
    "sep": "Сен", "oct": "Окт", "nov": "Ноя", "dec": "Дек",
}
MONTH_ORDER = ["sep", "oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug"]

def detect_months(company_row: dict) -> list:
    months = []
    for key in company_row.keys():
        if key.startswith("share_pay_"):
            suffix = key.replace("share_pay_", "")
            if suffix in MONTH_NAMES:
                months.append(suffix)
    months.sort(key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99)
    return months

def build_company_context(company_info: dict) -> str:
    months = detect_months(company_info)
    context = f"══════════════════════════════\n"
    context += f"Компания: {company_info['name']}\n"
    context += f"ИНН: {company_info['inn']}\n\n"
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
    "Хабаровский край": [], # Добавьте ID пользователей
    "Приморский край": [],
    "Сахалинская область": [],
    "Еврейская автономная область": [],
    "Амурская область": [],
    "Чукотский автономный округ": [],
    "Камчатский край": [],
    "Магаданская область": [],
}

# ... (Остальной код аналогичен newsendingbot) ...

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
    # Логика обработки
    pass

async def main():
    logger.info("INN Experiment Bot (Telethon) запускается...")
    await client.start(bot_token=BOT_TOKEN)
    logger.info("Бот на связи!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
