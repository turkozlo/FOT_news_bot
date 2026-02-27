import time
import requests
from bs4 import BeautifulSoup
import feedparser

websites = [
      {
        "url": "https://kamgov.ru/news",
        "selectors": [".row.news-list__item"]
      },
      {
        "url": "https://kamgov.ru/governor/view?id=98", 
        "selector": ".governor-news"
      }
]

total = len(websites)
successful = 0
failed = 0

for website in websites:
    url = website['url']
    print(f"\nПроверка {url}")

    if 'rss_url' in website:
        rss_url = website['rss_url']
        print(f"  RSS URL: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                print("  RSS-лента успешно разобрана, записи найдены.")
                successful += 1
                # print(feed.entries)
            else:
                print("  RSS-лента разобрана, но записей нет.")
                failed += 1
        except Exception as e:
            print(f"  Ошибка при разборе RSS-ленты: {e}")
            failed += 1

    elif 'selectors' in website:
        selectors = website['selectors']
        print(f"  Селекторы: {selectors}")
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                all_elements = []

                for selector in selectors:
                    elements = soup.select(selector)
                    print(f"\tНайдено по селектору '{selector}': {len(elements)} элементов.")
                    all_elements.extend(elements)

                if all_elements:
                    print(f"  Всего найдено элементов: {len(all_elements)}")
                    successful += 1
                    # print(all_elements)
                else:
                    print("  Ни один из селекторов не дал результатов.")
                    failed += 1
            else:
                print(f"  Не удалось загрузить URL: {response.status_code}")
                failed += 1
        except Exception as e:
            print(f"  Ошибка при загрузке или разборе HTML: {e}")
            failed += 1
    else:
        print("  Не указан ни RSS URL, ни селекторы.")
        failed += 1

    time.sleep(1)

print(f"\nИтог: Всего сайтов: {total}, Успешно: {successful}, Неудачно: {failed}")
