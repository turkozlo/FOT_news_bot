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

def test_leadership():
    test_cases = [
        {
            "name": "New Director at Large Factory - Should Recommend Meeting",
            "text": "На заводе 'АмурСталь' назначен новый генеральный директор Иван Петров. Ранее он возглавлял...",
            "expected_phrase": "Встретиться с новым руководителем"
        },
        {
            "name": "New Manager at Small Shop - Should Ignore (Thresholds)",
            "text": "В магазине 'Продукты' сменился управляющий. Теперь это Анна Сидорова.",
            "expected_phrase": "Нет предложений" 
        },
        {
            "name": "New CEO at Company (Unknown Scale) - Should Recommend Meeting",
            "text": "В компании 'ТехноГрупп' сменился генеральный директор. Им стал Сергей Сергеев.",
            "expected_phrase": "Встретиться с новым руководителем"
        }
    ]

    # Force UTF-8 encoding for stdout
    sys.stdout.reconfigure(encoding='utf-8')

    print("=== STARTING LEADERSHIP TEST ===\n")
    
    for case in test_cases:
        print(f"--- Testing: {case['name']} ---")
        print(f"News Text: {case['text'][:100]}...")
        
        result = generate_offer(case['text'], SYSTEM_PROMPT)
        
        print(f"Result: {result}")
        
        if result is None:
             print("LLM Error or None returned")
             continue
        
        if case['expected_phrase'] == "Нет предложений":
             if "Нет предложений" in result:
                 print("PASSED (Correctly ignored)")
             else:
                 print("FAILED (Should have been ignored)")
        else:
            if case['expected_phrase'] in result:
                print(f"PASSED (Found phrase '{case['expected_phrase']}')")
            else:
                print(f"FAILED (Did NOT find phrase '{case['expected_phrase']}')")
        print("\n")

if __name__ == "__main__":
    test_leadership()
