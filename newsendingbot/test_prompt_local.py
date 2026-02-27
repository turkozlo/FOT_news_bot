import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from newsendingbot.offer_generator import generate_offer
# from newsendingbot.main import SYSTEM_PROMPT

def get_system_prompt():
    with open("newsendingbot/main.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Simple extraction assuming SYSTEM_PROMPT is defined with triple quotes
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

def test_prompt():
    test_cases = [
        {
            "name": "General News (Should be ignored)",
            "text": "В правительстве прошла встреча с представителями малого бизнеса. Обсуждали меры поддержки и развитие отрасли в целом. Никаких конкретных решений по отдельным компаниям принято не было.",
            "expected_negative": True
        },
        {
            "name": "Specific News WITHOUT Client Name (Should be ignored)",
            "text": "В Хабаровском крае открылся новый завод по переработке рыбы. Ожидается создание 50 новых рабочих мест. Инвестор планирует расширение.",
            "expected_negative": True
        },
        {
            "name": "Specific News WITH Client Name (Should have recommendation)",
            "text": "Компания 'Восток-Рыба' открыла новый цех в Владивостоке. Директор Иван Иванов сообщил о наборе 100 сотрудников.",
            "expected_negative": False
        }
    ]

    # Force UTF-8 encoding for stdout
    sys.stdout.reconfigure(encoding='utf-8')

    print("=== STARTING PROMPT TEST ===\n")
    
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
    test_prompt()
