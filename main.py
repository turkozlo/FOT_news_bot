# main.py

import asyncio
import json
from typing import Dict
import datetime
import importlib

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest

from src.deduplicator import Deduplicator
from src.llm_classifier import classify_department, rate_engagement
from src.logger import log_action, log_error
from src.router import get_target_channel
from src.summarizer import summarize_text
from src.processor import handle_entry, batcher, deduper

# Загрузка конфигурации
with open('config/config.json', 'r', encoding='utf-8-sig') as config_file:
    config = json.load(config_file)

# Словарь: имя канала -> ID последнего обработанного сообщения
last_ids: Dict[str, int] = {}

# Инициализация модулей
interval = config.get('batch_interval_minutes', 10)


# Создание Telethon клиента (user.session)
session_name = config.get('session_file', 'user.session')
client = TelegramClient(
    session_name,
    api_id=config['api_id'],
    api_hash=config['api_hash'],
)


async def handle_message(msg, chat_username: str):
    """
    Обработка одного сообщения:
    - дедупликация
    - суммаризация
    - классификация (несколько департаментов)
    - оценка интересности
    - добавление в очередь batcher
    """
    text = getattr(msg, 'message', msg.text) or ""
    if not text:
        return

    # Обновляем ID последнего сообщения
    last_ids[chat_username] = msg.id

    # Дедупликация: пропускаем, если дубликат
    if deduper.is_duplicate(text):
        return
    deduper.add(text)

    # Логируем получение новости
    link = f"https://t.me/{chat_username}/{msg.id}"
    log_action('GET', text, f"@{chat_username}")

    # Получаем список департаментов (>=1 элемент)
    departments = await classify_department(text)
    print(departments)
    if departments == ['Без категории']:
        # На всякий случай, хотя из функции всегда возвращается минимум ['Без категории']
        return
    print(departments)
    # Для каждого департамента делаем суммаризацию и оценку и отправляем в batcher
    for dept in departments:
        summary    = await summarize_text(text, dept)
        print(summary)

        # Пропускаем, если суммаризатор вернул пустой ответ
        if not summary or "Пустой ответ" in summary:
            continue

        engagement = await rate_engagement(text, str(dept))
        print(engagement)

        payload = (
            f"{summary or text[:200] + '…'}\n\n"
            f"🔗 Оригинал: {link}\n"
            f"👀 Интересность: {engagement}\n"
        )
        target = get_target_channel(dept)
        batcher.add(payload, target, engagement)


@client.on(events.NewMessage(chats=config['source_channels']))
async def forward(event):
    """Хендлер для новых сообщений из указанных каналов"""
    username = event.chat.username or str(event.chat.id)
    await handle_message(event.message, username)


async def refill_missed():
    """
    Фоновая задача: дозапрашивает пропущенные сообщения
    при кратковременных разрывах соединения
    """
    await client.connect()
    interval_sec = config.get('refill_interval_seconds', 60)

    while True:
        await asyncio.sleep(interval_sec)
        total_new = 0

        for channel in config['source_channels']:
            uname = channel.lstrip('@')
            try:
                entity = await client.get_entity(uname)
                last_id = last_ids.get(uname, 0)
                new_count = 0

                async for msg in client.iter_messages(entity, min_id=last_id):
                    await handle_message(msg, uname)
                    new_count += 1

                if new_count:
                    print(f"[REFILL] {channel}: обработано {new_count} новых сообщений")
                total_new += new_count

            except Exception as error:
                print(f"[REFILL ERROR] {channel}: {error}")

        if total_new:
            print(f"[REFILL] Всего обработано {total_new} новых сообщений за цикл")


async def init_last_ids():
    """
    Инициализация словаря last_ids: сохраняем ID последнего сообщения
    для каждого канала при старте бота
    """
    for channel in config['source_channels']:
        uname = channel.lstrip('@')
        try:
            entity = await client.get_entity(uname)
            messages = await client.get_messages(entity, limit=1)
            last_ids[uname] = messages[0].id if messages else 0
            print(f"[INIT] {channel}: last_id = {last_ids[uname]}")
        except Exception as error:
            print(f"[INIT ERROR] {channel}: {error}")
            last_ids[uname] = 0

async def daily_cleanup():
    """
    Каждый день в полночь очищает файл очереди.
    """
    path = config.get('news_file', 'logs/queue_for_distribution.json')
    while True:
        now = datetime.datetime.now()
        # рассчитываем, сколько секунд до следующей полуночи
        tomorrow = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        wait_secs = (tomorrow - now).total_seconds()
        await asyncio.sleep(wait_secs)

        # чистим файл
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"[CLEANUP] {path} очищен в {tomorrow.date()}")
        except Exception as e:
            print(f"[CLEANUP ERROR] Не удалось очистить {path}: {e}")
        # сразу перейдём к следующей итерации (следующей полуночи)


async def poll_parser():
    from src.parsers.iabir_lenta_parser import parse
    interval = config.get("parser_interval_seconds", 600)

    while True:
        entries = await parse()
        for e in entries:
            await handle_entry(e)
        await asyncio.sleep(interval)


async def main():
    """
    Основная функция:
    - запуск сессии пользователя
    - инициализация last_ids
    - запуск фоновых задач refill и batcher
    - ожидание сообщений
    """
    print("Запускаем сессию пользователя…")
    await client.start(phone=config['phone'])
    print("✅ Сессия пользователя активна")

    print(f"[BATCH] Интервал отправки: {interval} мин")
    await init_last_ids()

    # Запуск фоновых тасков
    asyncio.create_task(refill_missed())
    asyncio.create_task(daily_cleanup())
    await batcher.start(client)
    print('🚀 Бот запущен и ожидает сообщений...')

    asyncio.create_task(poll_parser())
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())