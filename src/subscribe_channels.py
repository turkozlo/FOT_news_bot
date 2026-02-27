import asyncio
import json
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import UserAlreadyParticipantError, ChannelPrivateError, RPCError
from telethon.tl.functions.channels import JoinChannelRequest

# Загрузка конфигурации
with open('config/config.json', 'r', encoding='utf-8') as config_file:
    cfg = json.load(config_file)


async def main():
    api_id       = cfg["api_id"]
    api_hash     = cfg["api_hash"]
    session_file = cfg.get("session_file", "user.session")
    channels     = cfg.get("source_channels", [])

    client = TelegramClient(session_file, api_id, api_hash)
    await client.start(phone=cfg.get("phone"))

    print("Начинаем подписываться на каналы…")
    for chan in channels:
        username = chan.lstrip("@")
        try:
            await client(JoinChannelRequest(username))
            print(f"✅ Подписались на @{username}")
        except UserAlreadyParticipantError:
            print(f"ℹ️ Уже подписаны на @{username}")
        except ChannelPrivateError:
            print(f"⚠️ Не удалось подписаться на @{username}: канал приватный или закрыт")
        except RPCError as e:
            print(f"❌ Ошибка при подписке на @{username}: {e}")
        # небольшая пауза, чтобы не спамить API
        await asyncio.sleep(1)

    await client.disconnect()
    print("Готово.")

if __name__ == "__main__":
    asyncio.run(main())
