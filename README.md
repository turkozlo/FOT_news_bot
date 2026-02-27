# Channel News Bot

Автоматизированный Telegram-бот для сбора новостей из каналов и сайтов Дальневосточного федерального округа, их дедупликации, классификации по департаментам, краткого резюме и буферной отправки в соответствующие целевые каналы.

---

## 📂 Структура проекта
```
chanel_news_bot/
├── config/
│ ├── config.json # Основные настройки бота
│ ├── config_project.json # Настройки путей для Deduplicator
│ ├── llm_config.json # Настройки LLM (OpenAI / LangChain)
│ └── prompts.json # Тексты промптов для LLM
├── logs/ # Логи и файлы очередей (игнорируются git’ом)
│ ├── bot_logs.xlsx
│ ├── pending_news.json
│ ├── queue_for_distribution.json
│ └── duplicates.json
├── src/ # Исходники модулей
│ ├── batcher.py # Буферная отправка сообщений по расписанию
│ ├── deduplicator.py # Дедупликация (SentenceTransformer + JSON)
│ ├── llm_classifier.py # Классификация департаментов + рейтинг
│ ├── logger.py # Запись событий и ошибок в Excel
│ ├── metrics.py # Скрипт для расчёта weighted/macro‑метрик
│ ├── router.py # Сопоставление департамента → целевой канал
│ ├── smeshariki.py # Пример парсера сайтов (RSS/HTML)
│ └── summarizer.py # Краткое резюме новости через LLM
├── main.py # Точка входа: запускает Telethon‑бота, фоновые задачи
├── README.md # Документация (этот файл)
└── requirements.txt # Python‑зависимости
```


---

## 🚀 Быстрый старт

1. Склонируйте репозиторий и перейдите в папку:
   ```bash
   git clone git@github.com:YOUR_USERNAME/chanel_news_bot.git
   cd chanel_news_bot
   ````
2. Создайте и активируйте виртуальное окружение:
```
    python3 -m venv venv
    source venv/bin/activate
```
3. Установите зависимости:
```
    pip install -r requirements.txt
```
4. Заполните конфиги (в папке config/) своими данными:
```
config.json — основные настройки (API ID/Hash, список source/department каналов, телефон, интервалы).
llm_config.json — ключи и модели OpenAI / LangChain.
prompts.json — тексты промптов для классификации, суммаризации и рейтинга.
config_project.json — путь к файлу очереди (queue_for_distribution.json).
```
5. Запустите бота:
```
    python main.py
```
## 🔧 Конфигурация
### config/config.json
```
{
  "api_id": "*****",
  "api_hash": "*****",
  "source_channels": [
    "@channel1", "@channel2", ...
  ],
  "department_channels": {
    "IT Безопасность": "@it_security_channel",
    "Региональный Госсектор": "@gov_channel",
    "Бизнес": "@business_channel"
  },
  "phone": "*****",
  "batch_interval_minutes": 50,
  "max_per_batch": 5,
  "refill_interval_seconds": 60,
  "dedup_threshold": 0.83
}
```
source_channels — откуда читаем новости.

department_channels — куда отправлять по департаменту.

batch_interval_minutes — как часто шлём в целевые каналы.

max_per_batch — сколько топ‑новостей за раз.

refill_interval_seconds — период дозапроса пропущенных сообщений.

dedup_threshold — порог косинусного сходства для дедупликации.

### config/llm_config.json
```
{
  "api_key_Open_AI": "*****",
  "base_url_Open_AI": "https://api.openai.com/v1",
  "model_Open_AI": "gpt-4",
  "api_key_LANGCHAIN": "*****",
  "model_LANGCHAIN": "llama3-8b-8192",
  "llm_backend": 0  // 0 — OpenAI, 1 — LangChain
}
```

### config/prompts.json
```
{
  "classification": "Ты — классификатор новостей для внутренней аналитики компании. У тебя есть список департаментов: {departments}…",
  "summary":        "Ты — помощник, делающий краткие резюме новостных сообщений для департамента «{department}»…",
  "rating":         "Оцени, насколько новость может быть интересна аудитории департамента «{department}»…"
}
```

## 🧱 Основные модули
### src/deduplicator.py
SentenceTransformer (`all-MiniLM-L12-v2`)

Предобработка текста (lower, удаление ссылок/пунктуации)

`is_duplicate(text) → bool`

add(text) — сохраняет текст + эмбеддинг

### src/llm_classifier.py
Выбор backend (`OpenAI / LangChain`)

`classify_department(text) → list[str]`

`rate_engagement(text, department) → int`

### src/summarizer.py
`summarize_text(text, department) → str`

### src/batcher.py
Очередь в `pending_news.json`

`_periodic_send():`

1. Группировка по target
2. Сортировка по engagement
3. Топ N
4. Отправка единым сообщением

### src/router.py
`get_target_channel(department) → str`

### src/logger.py
`log_action(type, message, channel) → Excel`

`log_error(error)`

## 🛠 main.py
1. Инициализация:
* Загружает конфиг

* Стартует Deduplicator и Batcher

* Создаёт Telethon-клиента с user-сессией

2Init last_ids 
* При старте берёт последний ID каждого source‑канала, чтобы не дублировать старые.

3. Обработчик новых сообщений

* `@client.on(NewMessage(chats=source_channels))`

* `handle_message()`: дедупликация → классификация → суммари → рейтинг → добавление в batcher

4. Фоновые задачи

* `refill_missed()`— дозапрашивает пропущенные сообщения каждые N секунд

* `daily_cleanup()`— каждый день в полночь очищает очередь queue_for_distribution.json

5. Запуск
```
asyncio.run(main())
```
## 📊 Метрики качества (src/metrics.py)
* `Weighted Accuracy` = среднее значение Score ∈ {0, 0.5, 1}

* `Macro‑Score` = среднее по трём департаментам, где каждый даёт своё среднее Score

<hr>

# 🧨 Расширение парсера с новостных tg каналов на сайты

Чтобы добавить любой парсер‑функцию (RSS, HTML, CSV или что угодно) без правок «ядра» бота, достаточно:
1. `Определить` простой контракт для парсера:
Любой твой парсер-код (в отдельном файле) должен экспортировать одну функцию:
```commandline
# src/parsers/rss_parser.py

async def parse() -> list[dict]:
    """
    Возвращает список записей вида:
    [
      {
        "id": str|int,    # уникальный идентификатор записи
        "text": str,      # её текст
        "link": str       # URL или любая ссылка для логирования
      },
      ...
    ]
    """
    # …твой код: грузим RSS, парсим, фильтруем по дате и т.п.…
    return entries
```
2. Вынести логику обработки в общий метод handle_entry, чтобы она не была завязана только на Telethon:
```commandline
# src/processor.py

from src.deduplicator import Deduplicator
from src.llm_classifier import classify_department, rate_engagement
from src.summarizer import summarize_text
from src.router import get_target_channel
from src.batcher import Batcher
from src.logger import log_action

deduper = Deduplicator()
batcher = Batcher(interval_minutes=10)

async def handle_entry(entry: dict):
    uid  = entry["id"]
    text = entry["text"]
    link = entry["link"]

    # Дедупликация по UID (или по text)
    if deduper.is_duplicate(uid):
        return
    deduper.add(uid)

    # Логируем
    log_action("GET", text, link)

    # Классификация может вернуть несколько департаментов
    depts = classify_department(text)
    for dept in depts:
        summary = summarize_text(text, dept)
        score   = rate_engagement(text, dept)

        payload = (
            f"{summary or text[:200] + '…'}\n\n"
            f"🔗 Источник: {link}\n"
            f"Категория: {dept}\n"
            f"Интерес: {score}/10"
        )
        target = get_target_channel(dept)
        batcher.add(payload, target, score)

```
3. В main.py запустить и Telethon‑обработчик, и парсер‑функцию:
```
# main.py

import asyncio
import json
from telethon import TelegramClient, events
from pathlib import Path
from src.processor import handle_entry
import importlib

# Загружаем config
cfg_path = Path("config/config.json")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

# Telethon client
client = TelegramClient(cfg["session_file"], cfg["api_id"], cfg["api_hash"])

@client.on(events.NewMessage(chats=cfg["source_channels"]))
async def on_telegram(event):
    entry = {
        "id":   event.message.id,
        "text": event.message.message or event.message.text,
        "link": f"https://t.me/{event.chat.username}/{event.message.id}"
    }
    await handle_entry(entry)

# Задача для парсера
async def poll_parser():
    # динамический импорт: fname без .py
    parser_module = importlib.import_module("src.parsers." + cfg["parser_file"])
    parse_fn = getattr(parser_module, "parse")

    interval = cfg.get("parser_interval_seconds", 300)
    while True:
        try:
            entries = await parse_fn()
            for ent in entries:
                await handle_entry(ent)
        except Exception as e:
            print("[PARSER ERROR]", e)
        await asyncio.sleep(interval)

async def main():
    await client.start(phone=cfg["phone"])
    # Запускаем парсер
    asyncio.create_task(poll_parser())
    # Запускаем батчер (он внутри себя ждёт событий)
    # Предположим, batcher.start(client) поднимет его
    from src.batcher import Batcher
    batcher = Batcher(interval_minutes=cfg["batch_interval_minutes"])
    await batcher.start(client)
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
```
4. Настроить config/config.json:
```commandline
{
  "api_id":           "*****",
  "api_hash":         "*****",
  "session_file":     "user.session",
  "phone":            "*****",
  "source_channels":  ["@channel1", "@channel2"],
  "batch_interval_minutes": 10,
  // Имя файла парсера без .py, файл должен лежать в src/parsers/
  "parser_file":            "rss_parser",
  "parser_interval_seconds": 600
}
```
## ✅ Добавление нового парсера
1. Создать файл src/parsers/html_parser.py.

2. В нём описать async def parse() -> list[dict]: ….

3. В config.json поставить "parser_file": "html_parser".

4. Перезапустить бота — новый источник автоматически начнёт обрабатываться теми же steps:
dedup, LLM‑классификация, суммаризация, батчинг.

Таким образом, ядро (processor.py, main.py, batcher, deduper и т. д.) остаётся без изменений. Новые парсер‑файлы вы просто добавляете и указываете их в конфиге.