# src/parsers/riabir_lenta_parser.py

import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict

BASE_URL = "https://riabir.ru"
LENTA_URL = f"{BASE_URL}/lenta/"

async def parse() -> List[Dict]:
    """
    Парсит новости с riabir.ru/lenta/, берёт только <a rel="bookmark"> внутри .post-title
    и возвращает список записей:
    [
      {"id": <URL>, "text": <заголовок>, "link": <URL>},
      ...
    ]
    """
    entries = []
    async with aiohttp.ClientSession() as session:
        async with session.get(LENTA_URL, timeout=10) as resp:
            html = await resp.text(encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")

    # Проходим по каждому контейнеру .post-title
    for block in soup.select("div.post-title"):
        # Ищем внутри именно <a rel="bookmark">
        a = block.select_one('a[rel="bookmark"]')
        if not a:
            continue

        href = a["href"]
        link = href if href.startswith("http") else BASE_URL + href
        title = a.get_text(strip=True)

        entries.append({
            "id": link,   # используем URL как уникальный ID
            "text": title,
            "link": link
        })

    return entries


if __name__ == "__main__":
    import asyncio

    async def main():
        entries = await parse()
        for i, e in enumerate(entries, 1):
            print(f"{i}. ID:   {e['id']}")
            print(f"   Text: {e['text']}")
            print(f"   Link: {e['link']}\n")

    asyncio.run(main())