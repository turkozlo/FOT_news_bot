import logging
import json
from pathlib import Path
from telethon import TelegramClient, events

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

# Множество для предотвращения дублей
processed_messages = set()

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
