
import re

def normalize_name(name):
    """
    Removes quotes, legal prefixes, and extra spaces.
    """
    n = name.lower()
    # Remove quotes
    n = re.sub(r"['\"«»]", "", n)
    # Remove common legal prefixes (optional, but good for "ООО Ромашка" -> "Ромашка")
    # Be careful not to remove "Завод" if it's part of the common name
    n = re.sub(r"\b(ооо|ао|пао|зао|ип)\b", "", n)
    # Remove punctuation
    n = re.sub(r"[^\w\s]", " ", n)
    # Normalize spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n

def search_company(text, db):
    # Normalize text ONCE
    text_norm = normalize_name(text)
    print(f"Normalized Text: '{text_norm}'")
    
    found = []
    for clean_name, original_data in db.items():
        # strict substring search of cleaned name in cleaned text
        if clean_name in text_norm:
            found.append(original_data)
            print(f"MATCH: '{clean_name}' found in text.")
        else:
            print(f"NO MATCH: '{clean_name}' not in text.")
    return found

# Mock DB
raw_companies = [
    {"name": "ООО Ромашка", "inn": "1"},
    {"name": "Завод «Звезда»", "inn": "2"}, # CSV might have quotes too
    {"name": "ИП Иванов", "inn": "3"}
]

DB = {}
for c in raw_companies:
    clean = normalize_name(c["name"])
    DB[clean] = c
    print(f"DB Entry: '{c['name']}' -> Key: '{clean}'")

# Test Cases
texts = [
    "Завод «Звезда» инвестирует 208+ млн рублей...",
    "Компания «Ромашка» инвестирует 208+ млн рублей...",
    "ИП Иванов открыл точку...",
    "Просто текст без всего"
]

for t in texts:
    print(f"\nTesting: '{t}'")
    search_company(t, DB)
