import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from newsendingbot.offer_generator import generate_offer

# Helper to get prompt without importing main
def get_system_prompt():
    with open("newsendingbot/main.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    start_marker = 'SYSTEM_PROMPT = """'
    end_marker = '"""'
    
    start_idx = content.find(start_marker)
    if start_idx == -1:
        raise ValueError("Could not find SYSTEM_PROMPT in main.py")
    
    start_idx += len(start_marker)
    end_idx = content.find(end_marker, start_idx)
    
    if end_idx == -1:
        raise ValueError("Could not find end of SYSTEM_PROMPT in main.py")
        
    return content[start_idx:end_idx]

SYSTEM_PROMPT = get_system_prompt()

def test_thresholds():
    test_cases = [
        {
            "name": "Small Investment (5M RUB) - Should Ignore",
            "text": "Компания 'Рога и Копыта' получила грант в размере 5 миллионов рублей на закупку оборудования.",
            "expected_negative": True
        },
        {
            "name": "Large Investment (15M RUB) - Should Recommend",
            "text": "Завод 'БетонСтрой' инвестирует 15 миллионов рублей в модернизацию цеха.",
            "expected_negative": False
        },
        {
            "name": "Few Jobs (2 jobs) - Should Ignore",
            "text": "ИП Сидоров открыл киоск и нанял 2 продавцов.",
            "expected_negative": True
        },
        {
            "name": "Many Jobs (10 jobs) - Should Recommend",
            "text": "Ресторан 'Вкусно' открывается в центре и ищет 10 сотрудников.",
            "expected_negative": False
        },
        {
            "name": "Implied Small Scale (Sewing machine grant) - Should Ignore",
            "text": "Предприниматель Анна Петрова выиграла грант на покупку швейной машинки для своего ателье.",
            "expected_negative": True
        },
        {
            "name": "Implied Large Scale (New Mall) - Should Recommend",
            "text": "Компания 'Девелопмент-Групп' начала строительство нового торгового центра 'Плаза'.",
            "expected_negative": False
        }
    ]

    # Force UTF-8 encoding for stdout
    sys.stdout.reconfigure(encoding='utf-8')

    print("=== STARTING THRESHOLD TEST ===\n")
    
    for case in test_cases:
        print(f"--- Testing: {case['name']} ---")
        print(f"News Text: {case['text'][:100]}...")
        
        result = generate_offer(case['text'], SYSTEM_PROMPT)
        
        print(f"Result: {result}")
        
        if result is None:
             print("LLM Error or None returned")
             continue

        is_negative = "Нет предложений" in result
        
        if case['expected_negative']:
            if is_negative:
                print("PASSED (Correctly ignored)")
            else:
                print("FAILED (Should have been ignored but got recommendation)")
        else:
            if not is_negative:
                print("PASSED (Got recommendation)")
            else:
                print("FAILED (Should have got recommendation but was ignored)")
        print("\n")

if __name__ == "__main__":
    test_thresholds()
