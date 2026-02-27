import os
import re
import json
from sentence_transformers import SentenceTransformer, util

# Загрузка конфига
with open('config/config_project.json', 'r', encoding='utf-8-sig') as f:
    cfg = json.load(f)

NEWS_FILE = cfg.get('news_file', 'logs/queue_for_distribution.json')


class Deduplicator:
    def __init__(self, threshold=0.85, news_file=None):
        self.threshold = threshold
        self.news_file = news_file or NEWS_FILE
        self.model = SentenceTransformer('all-MiniLM-L12-v2')
        self.seen_texts = self._load_existing()
        print(f"[DEDUP] Загружено {len(self.seen_texts)} старых новостей")

    def _preprocess(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'https?://\S+', '', text)  # удаляем ссылки
        text = re.sub(r'[^\w\s]', '', text)       # удаляем пунктуацию
        text = re.sub(r'\s+', ' ', text)          # удаляем лишние пробелы
        return text.strip()

    def _load_existing(self):
        if not os.path.exists(self.news_file):
            print("[DEDUP] Файл не найден, старт с пустого списка")
            return []

        try:
            with open(self.news_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[DEDUP] Ошибка при загрузке: {e}")
            return []

    def _save(self):
        try:
            with open(self.news_file, 'w', encoding='utf-8') as f:
                json.dump(self.seen_texts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEDUP] Ошибка при сохранении: {e}")

    def is_duplicate(self, new_text: str) -> bool:
        if not self.seen_texts:
            return False

        new_text_clean = self._preprocess(new_text)
        new_emb = self.model.encode(new_text_clean).tolist()

        # Сравнение только с последними 100 новостями
        recent_entries = self.seen_texts[-1000:]
        old_embs = [entry['embedding'] for entry in recent_entries]

        cosine_scores = util.cos_sim([new_emb], old_embs)[0]
        max_sim = max(cosine_scores).item()

        print(f"[DEDUP] Макс. сходство: {max_sim:.3f}")
        return max_sim >= self.threshold

    def add(self, new_text: str):
        new_text_clean = self._preprocess(new_text)
        embedding = self.model.encode(new_text_clean).tolist()

        self.seen_texts.append({
            'text': new_text,
            'embedding': embedding
        })
        self._save()


if __name__ == "__main__":
    print("🔧 Запуск теста Deduplicator...")

    test_file = 'logs/test_queue.json'
    cfg['news_file'] = test_file
    NEWS_FILE = test_file

    if os.path.exists(test_file):
        os.remove(test_file)

    dedup = Deduplicator(threshold=0.9)

    news_1 = "Компания X анонсировала выход новой версии продукта"
    news_2 = "Компания X представила новую версию своего продукта"
    news_3 = "Вышел отчет об уязвимостях в ПО компании Y"

    print("\n➡ Добавляем первую новость")
    assert not dedup.is_duplicate(news_1), "news_1 не должна быть дубликатом"
    dedup.add(news_1)

    print("➡ Проверяем почти дубликат второй новости")
    assert dedup.is_duplicate(news_2), "news_2 должна считаться дубликатом"

    print("➡ Проверяем третью новость (уникальную)")
    assert not dedup.is_duplicate(news_3), "news_3 должна быть уникальной"
    dedup.add(news_3)

    print("✅ Все тесты прошли успешно.")

    if os.path.exists(test_file):
        os.remove(test_file)
