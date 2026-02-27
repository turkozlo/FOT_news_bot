import json
import asyncio
from datetime import datetime

PENDING_FILE = 'logs/pending_news.json'

class Batcher:
    def __init__(self, interval_minutes: int = 10, max_per_batch: int | None = None):
        self.interval = interval_minutes * 60
        self.max_per_batch = max_per_batch
        try:
            with open(PENDING_FILE, 'r', encoding='utf-8-sig') as f:
                self.pending = json.load(f)
        except Exception:
            self.pending = []

    async def start(self, client):
        self.client = client
        asyncio.create_task(self._periodic_send())

    async def _periodic_send(self):
        while True:
            await asyncio.sleep(self.interval)
            if not self.pending:
                continue

            # Группировка по целевым каналам
            grouped: dict[str, list[dict]] = {}
            for entry in self.pending:
                grouped.setdefault(entry["target"], []).append(entry)

            # Сброс текущей очереди сразу, чтобы не дублировать при ошибке
            self.pending = []
            self._save()

            for target, messages in grouped.items():
                try:
                    # Сортировка по интересности
                    sorted_msgs = sorted(
                        messages,
                        key=lambda x: x.get("engagement", 5),
                        reverse=True
                    )
                    # Отбираем только top-N
                    if self.max_per_batch is not None:
                        sorted_msgs = sorted_msgs[: self.max_per_batch]

                    # Убираем дубликаты текста
                    seen_texts = set()
                    unique_parts = []
                    for msg in sorted_msgs:
                        txt = msg['text']
                        if txt not in seen_texts:
                            seen_texts.add(txt)
                            unique_parts.append(txt)

                    # Финальный текст
                    header = "🔥 Топ новостей за последнее время:\n\n"
                    full_text = header + "\n\n──────────\n\n".join(unique_parts)

                    await self.client.send_message(target, full_text[:4090], link_preview=False)

                except Exception as e:
                    print(f"[BATCHER] Ошибка при отправке: {e}")
                    self.pending.extend(messages)

            self._save()

    def add(self, text: str, target: str, engagement: int):
        if engagement < 5:
            return  # 🔴 Игнорируем неинтересные сообщения

        entry = {
            "text": text,
            "target": target,
            "ts": datetime.now().isoformat(),
            "engagement": engagement
        }
        self.pending.append(entry)
        self._save()

    def _save(self):
        with open(PENDING_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.pending, f, ensure_ascii=False, indent=2)