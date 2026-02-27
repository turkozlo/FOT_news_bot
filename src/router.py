import json

def load_department_channels():
    with open('config/config.json', 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)
    return cfg.get('department_channels', {})


def get_target_channel(department: str) -> str:
    mapping = load_department_channels()
    print(f"[DEBUG] Для департамента «{department}» выбран канал «{mapping.get(department, mapping.get('Без категории'))}»")
    return mapping.get(department, mapping.get('Без категории'))