import logging
import json
import re
from pathlib import Path
from telethon import TelegramClient, events

from deduplicator import Deduplicator

# --- НАСТРОЙКИ ---
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.json"

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
        return json.load(f)

cfg = load_config()
API_ID = int(cfg['api_id']) if str(cfg.get('api_id', '')).isdigit() else 0
API_HASH = cfg.get('api_hash', '*****')
BOT_TOKEN = cfg.get('bot_token', '*****')

CHANNELS_MAPPING = {
    '@businessnews27': 20,
    '@RGSNIK27': 18,
    '@cyberbezopasnik': 2,
    '@lawyerDVB': 6,
    '@compliencenews': 16,
}

GROUP_ID = cfg.get('group_id', 0)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Множество для предотвращения дублей по ID
processed_messages = set()

# Дедупликация по URL (только запущенная сессия)
url_sent_global = set()

# Семантический дедубликатор (порог 0.82, без LLM-арбитра)
deduplicator = Deduplicator(
    threshold=0.82,
    news_file="dvbnewsbot/queue_for_distribution.json"
)

# Инициализация клиента Telethon в режиме бота (сессия внутри папки бота)
SESSION_NAME = str(Path(__file__).resolve().parent / "dvbnewsbot_session")
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handle_new_message(event):
    try:
        message = event.message
        
        # 1. Извлекаем источник (либо откуда переслано, либо сам канал)
        channel_id = None
        channel_username = None
        
        if message.fwd_from:
            # Если сообщение переслано
            if hasattr(message.fwd_from.from_id, 'channel_id'):
                channel_id = message.fwd_from.from_id.channel_id
            elif hasattr(message.fwd_from.from_id, 'chat_id'):
                channel_id = message.fwd_from.from_id.chat_id
        
        # Пытаемся определить имя канала или ID для маппинга
        sender = await event.get_chat()
        
        # Если это пост из канала (direct channel post)
        if hasattr(sender, 'username') and sender.username:
            channel_key = f"@{sender.username}"
        else:
            channel_key = str(event.chat_id)

        # Если сообщение переслано, нам важнее КТО ПЕРВОИСТОЧНИК
        if message.fwd_from:
             try:
                 original_channel = await client.get_entity(message.fwd_from.from_id)
                 if hasattr(original_channel, 'username') and original_channel.username:
                     channel_key = f"@{original_channel.username}"
                 else:
                     channel_key = str(original_channel.id)
             except Exception:
                 # Если не удалось получить сущность пересланного канала, пропускаем
                 pass

        if channel_key not in CHANNELS_MAPPING:
            return

        thread_id = CHANNELS_MAPPING[channel_key]
        
        # Уникальный ключ для дедупликации (канал + ID сообщения)
        msg_id = message.id if not message.fwd_from else message.fwd_from.channel_post
        message_key = f"{channel_key}_{msg_id}"

        if message_key in processed_messages:
            return
        processed_messages.add(message_key)
        
        # Очистка памяти от бесконечного роста множества ID
        if len(processed_messages) > 1000:
            list_ids = list(processed_messages)
            processed_messages.clear()
            processed_messages.update(list_ids[-500:])

        # --- ДОПОЛНИТЕЛЬНАЯ ДЕДУПЛИКАЦИЯ ---
        original_text = message.text or message.caption
        if not original_text:
            return
            
        # 1. Быстрая проверка по URL
        url_match = re.search(r'https?://t\.me/\S+', original_text)
        news_url = url_match.group(0).rstrip('.,) ') if url_match else None
        
        if news_url:
            if news_url in url_sent_global:
                logger.info(f"[DEDUP-URL] Пропускаем — URL уже был переслан: {news_url}")
                return
            url_sent_global.add(news_url)
            
        # 2. Семантическая проверка текста (если >= 0.82, значит дубль)
        max_sim, _ = deduplicator.get_max_similarity(original_text)
        if max_sim >= deduplicator.threshold:
            logger.info(f"[DEDUP-SEMANTIC] Пропускаем — Текст слишком похож на предыдущие (Сходство {max_sim:.3f} >= {deduplicator.threshold})")
            return
            
        deduplicator.add(original_text)
        # -----------------------------------

        # Пересылаем в группу в нужный топик
        await client.send_message(
            entity=GROUP_ID,
            message=message,
            reply_to=thread_id
        )

        logger.info(f"[FORWARDED] {channel_key} -> Thread {thread_id}")

    except Exception as e:
        logger.exception("Ошибка при обработке сообщения")

async def main():
    logger.info("DVB News Bot (Telethon) запускается...")
    await client.start(bot_token=BOT_TOKEN)
    logger.info("Бот на связи!")
    await client.run_until_disconnected()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
