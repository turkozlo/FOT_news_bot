
import csv
import re

# Mock the CSV loading logic from main.py
COMPANY_DB = {}
mock_csv_data = [
    {"inn": "2724225050", "name": "ООО Ромашка", "empl_pay_jan": "50", "share_pay_jan": "0.50"},
    {"inn": "2721098765", "name": "Завод Звезда", "empl_pay_jan": "200", "share_pay_jan": "0.80"},
]

for row in mock_csv_data:
    norm_name = row["name"].lower().strip()
    COMPANY_DB[norm_name] = row

def search_company_data(text: str):
    t = text.lower()
    print(f"Searching in text: '{t}'")
    found = []
    for name, data in COMPANY_DB.items():
        print(f"Checking against DB key: '{name}'")
        if name in t:
            found.append(data)
    return found

# Test cases from user
test_news_1 = "Завод «Звезда» инвестирует 208+ млн рублей..."
test_news_2 = "Компания «Ромашка» инвестирует 208+ млн рублей..."

print("--- Test 1 ---")
res1 = search_company_data(test_news_1)
print(f"Result 1: {res1}")

print("\n--- Test 2 ---")
res2 = search_company_data(test_news_2)
print(f"Result 2: {res2}")
