"""
Тест INN Experiment: подсовывает заранее подготовленные новости
вместо парсинга Telegram-каналов и прогоняет через LLM.

Использование:
    python INN_Experiment/test_inn_experiment.py

Скрипт:
1. Загружает company_data.csv
2. Для каждой тестовой новости ищет упоминание компании
3. Формирует контекст (как в боевом main.py)
4. Отправляет в LLM и выводит результат в консоль
"""

import sys
import os
import re
import csv
import asyncio

# --- Добавляем корневую папку проекта в путь ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)

# --- Импорт из INN_Experiment ---
# Переиспользуем offer_generator (он лежит в INN_Experiment)
sys.path.insert(0, os.path.join(ROOT_DIR, "INN_Experiment"))
from offer_generator import generate_offer_async

# ============================================================
# Дублируем ключевые функции из main.py чтобы тест был автономным
# ============================================================

MONTH_NAMES = {
    "jan": "Янв", "feb": "Фев", "mar": "Мар", "apr": "Апр",
    "may": "Май", "jun": "Июн", "jul": "Июл", "aug": "Авг",
    "sep": "Сен", "oct": "Окт", "nov": "Ноя", "dec": "Дек",
}
MONTH_ORDER = ["sep", "oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug"]


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r"['\"«»]", "", n)
    n = re.sub(r"\b(ооо|ао|пао|зао|ип)\b", "", n)
    n = re.sub(r"[^\w\d\s-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def load_company_data(csv_path="INN_Experiment/company_data.csv"):
    db = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean_key = normalize_name(row["name"])
            if clean_key:
                db[clean_key] = row
    print(f"[TEST] Загружено компаний: {len(db)}")
    return db


def search_company_data(text, db):
    t_norm = normalize_name(text)
    found = []
    for clean_name, data in db.items():
        if clean_name in t_norm:
            found.append(data)
    return found


def detect_months(company_row):
    months = []
    for key in company_row.keys():
        if key.startswith("share_pay_"):
            suffix = key.replace("share_pay_", "")
            if suffix in MONTH_NAMES:
                months.append(suffix)
    months.sort(key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99)
    return months


def build_company_context(company_info):
    months = detect_months(company_info)
    
    ctx = f"══════════════════════════════\n"
    ctx += f"Компания: {company_info['name']}\n"
    ctx += f"ИНН: {company_info['inn']}\n\n"
    ctx += "Помесячная статистика:\n"
    
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
        ctx += f"  {label}: {e_pay} с ФОТ из {total}, доля={share}, ср.ЗП={avg_sal}\n"
        try:
            shares.append(float(share))
        except:
            pass
    
    if len(shares) >= 2:
        first, last = shares[0], shares[-1]
        delta = round(last - first, 2)
        fm = MONTH_NAMES.get(months[0], months[0])
        lm = MONTH_NAMES.get(months[-1], months[-1])
        if delta < 0:
            trend = f"СНИЖЕНИЕ на {abs(delta)} ({fm}: {first} -> {lm}: {last})"
        elif delta > 0:
            trend = f"РОСТ на {delta} ({fm}: {first} -> {lm}: {last})"
        else:
            trend = f"СТАБИЛЬНО ({first})"
        ctx += f"\nТРЕНД ДОЛИ ФОТ: {trend}\n"
    
    ctx += f"══════════════════════════════\n\n"
    return ctx


def sanitize_llm_output(text):
    """Пост-обработка: markdown -> HTML"""
    if not text:
        return text
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<b>\1</b>', text)
    text = re.sub(r'```\w*\n?', '', text)
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    return text


# ============================================================
# SYSTEM_PROMPT (копия из main.py)
# ============================================================
SYSTEM_PROMPT = """
Ты — старший аналитик корпоративного блока банка.
Твоя задача — на основе текста новости и (если есть) внутренних данных о клиенте подготовить аналитическую рекомендацию для менеджера.

ФОРМАТ ВЫВОДА (КРИТИЧЕСКИ ВАЖНО):
- Пиши ТОЛЬКО простой текст с HTML-тегами (<b>жирный</b>).
- НИКОГДА не используй markdown.

ФИЛЬТРАЦИЯ:
- Нет названия компании -> «Нет предложений»
- Инвестиции < 10 млн или рабочих мест <= 3 -> «Нет предложений»
- Регион не из списка (Хабаровский, Приморский, Сахалинская, ЕАО, Амурская, Чукотский, Камчатский, Магаданская) -> «Нет предложений»

ТВОЯ СПЕЦИАЛИЗАЦИЯ — ТОЛЬКО ЗАРПЛАТНЫЙ ПРОЕКТ (ФОТ):
- Подключение ЗП-проекта
- Увеличение доли ФОТ
- Подключение новых сотрудников к ЗП-проекту
- Выяснение причин снижения доли ФОТ
НЕ ПРЕДЛАГАЙ другие банковские продукты (кредиты, РКО, эквайринг и т.д.).

Если есть [ДАННЫЕ О КЛИЕНТЕ ИЗ БАЗЫ]:

Ссылка на источник: ссылка
Краткое описание новости

<b>Клиент:</b> [Название] (ИНН [число])

<b>Аналитика:</b>
3-5 строк ВЫВОДОВ:
- Тренд доли ФОТ
- Ключевая проблема/возможность для ФОТ
- Потенциал из новости (новые рабочие места). Если точная цифра не указана — можешь предположить, но ОБЯЗАТЕЛЬНО пиши "предположительно" или "по предварительной оценке". Помни: далеко не все инвестиции идут на зарплаты.

<b>Рекомендация:</b>
Только по теме ФОТ:
1. Повод для контакта
2. Если доля ФОТ снижается — встреча + причины + увеличение
3. Если расширение — ЗП-проект для новых сотрудников
4. Если доля ФОТ растёт — закрепить + расширить

Если данных о клиенте НЕТ:
Краткая рекомендация по ФОТ.

ВАЖНО: ВСЕГДА указывай ИНН. НЕ придумывай цифр. НЕ предлагай продукты вне ФОТ. ТОЛЬКО HTML.
    """

# ============================================================
# ТЕСТОВЫЕ НОВОСТИ
# ============================================================
TEST_NEWS = [
    {
        "id": 1,
        "source": "https://t.me/ERDCnews/7777",
        "text": (
            "Компания «Ромашка» инвестирует 208+ млн рублей в создание "
            "металлоперерабатывающего предприятия в Приморском крае. "
            "Запуск намечен на 2026 год, предприятие будет использовать "
            "налоговые льготы и господдержку СПВ."
        ),
        "expected_company": "ООО Ромашка",
        "expected_trend": "СНИЖЕНИЕ",
    },
    {
        "id": 2,
        "source": "https://t.me/ERDCnews/8888",
        "text": (
            "Завод «Звезда» в Большом Камне объявил о расширении "
            "судостроительных мощностей. Планируется создание 150 новых "
            "рабочих мест в рамках гособоронзаказа."
        ),
        "expected_company": "Завод Звезда",
        "expected_trend": "РОСТ",
    },
    {
        "id": 3,
        "source": "https://t.me/prom_chukotka/9999",
        "text": (
            "Компания СтройМаш получила разрешение на строительство "
            "логистического центра в Хабаровске. Объём инвестиций — 500 млн руб., "
            "планируется 80 новых рабочих мест."
        ),
        "expected_company": "Компания СтройМаш",
        "expected_trend": "СНИЖЕНИЕ",
    },
    {
        "id": 4,
        "source": "https://t.me/sakhonline/1111",
        "text": (
            "ООО «Айсберг» запускает новую линию переработки морепродуктов "
            "на Сахалине. Инвестиции составят 120 млн рублей, будет создано "
            "50 рабочих мест."
        ),
        "expected_company": "ООО Айсберг",
        "expected_trend": "РОСТ",
    },
    {
        "id": 5,
        "source": "https://t.me/news_amur/2222",
        "text": (
            "В Амурской области откроется новый молочный завод. "
            "Инвестор не раскрывается, но объём инвестиций — 300 млн руб."
        ),
        "expected_company": None,  # Нет названия -> "Нет предложений"
        "expected_trend": None,
    },
    {
        "id": 6,
        "source": "https://t.me/ERDCnews/3333",
        "text": (
            "ООО «Ромашка» и Завод «Звезда» заключили соглашение о совместном "
            "строительстве промышленного парка в Приморском крае. Объём инвестиций — "
            "1.5 млрд руб., ожидается создание 300+ рабочих мест."
        ),
        "expected_company": "ООО Ромашка + Завод Звезда",  # Две компании!
        "expected_trend": "обе",
    },
]


# ============================================================
# ОСНОВНАЯ ЛОГИКА ТЕСТА
# ============================================================
async def run_test():
    db = load_company_data()
    
    print("=" * 70)
    print("  INN EXPERIMENT — ТЕСТОВЫЙ ПРОГОН")
    print(f"  Компаний в базе: {len(db)}")
    print(f"  Тестовых новостей: {len(TEST_NEWS)}")
    print("=" * 70)
    
    for news in TEST_NEWS:
        print(f"\n{'─' * 70}")
        print(f"ТЕСТ #{news['id']}: {news['text'][:80]}...")
        print(f"  Ожидаемая компания: {news['expected_company']}")
        print(f"  Ожидаемый тренд:    {news['expected_trend']}")
        print(f"{'─' * 70}")
        
        # 1. Поиск компании
        found = search_company_data(news["text"], db)
        
        if found:
            print(f"  [OK] Найдено компаний: {len(found)} -> {[c['name'] for c in found]}")
        else:
            print(f"  [--] Компаний не найдено")
        
        # 2. Формируем текст для LLM
        full_text = f"Ссылка на источник: {news['source']}\n{news['text']}"
        
        if found:
            full_text += "\n\n[ДАННЫЕ О КЛИЕНТЕ ИЗ БАЗЫ]\n"
            for c in found:
                ctx = build_company_context(c)
                full_text += ctx
                print(f"\n  [КОНТЕКСТ для '{c['name']}']")
                # Печатаем контекст компактно
                for line in ctx.strip().split("\n"):
                    print(f"    {line}")
        
        # 3. Отправляем в LLM
        print(f"\n  >>> Отправляю в LLM...")
        try:
            result = await generate_offer_async(full_text, SYSTEM_PROMPT)
            result = sanitize_llm_output(result)
            
            print(f"\n  <<< ОТВЕТ LLM:")
            print(f"  {'.' * 50}")
            if result:
                for line in result.strip().split("\n"):
                    print(f"  | {line}")
            else:
                print(f"  | [ПУСТОЙ ОТВЕТ]")
            print(f"  {'.' * 50}")
            
            # Проверки
            if news["expected_company"] is None:
                if result and "Нет предложений" in result:
                    print(f"  [PASS] Правильно отфильтровано")
                else:
                    print(f"  [WARN] Ожидалось 'Нет предложений'")
            else:
                if result and "ИНН" in result:
                    print(f"  [PASS] ИНН найден в ответе")
                else:
                    print(f"  [FAIL] ИНН НЕ найден в ответе!")
                    
        except Exception as e:
            print(f"  [ERROR] Ошибка LLM: {e}")
        
        # Пауза между запросами
        await asyncio.sleep(2)
    
    print(f"\n{'=' * 70}")
    print("  ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(run_test())
