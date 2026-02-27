# src/processor.py
import json

from src.batcher import Batcher
from src.deduplicator import Deduplicator
from src.logger import log_action
from src.llm_classifier import classify_department, rate_engagement
from src.router import get_target_channel

with open("config/config.json", "r", encoding="utf-8-sig") as f:
    conf = json.load(f)

# единый глобальный экземпляр
deduper = Deduplicator(conf.get('dedup_threshold', 0.95))
batcher = Batcher(interval_minutes=conf.get('batch_interval_minutes'), max_per_batch=conf.get('max_per_batch'))

async def handle_entry(entry: dict):
    text = entry["text"]
    link = entry["link"]

    # дедупликация по тексту
    if deduper.is_duplicate(text):
        return
    deduper.add(text)

    log_action("GET", text, link)

    depts = await classify_department(text)

    if "Без категории" in depts:
        return

    for dept in depts:
        score = await rate_engagement(text, dept)
        payload = (
            f"{text}\n\n"
            f"🔗 Оригинал: {link}\n"
            f"👀 Интересность : {score}\n"
        )
        target = get_target_channel(dept)
        batcher.add(payload, target, score)