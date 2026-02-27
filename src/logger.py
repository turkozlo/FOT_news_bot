import json
import pandas as pd
from datetime import datetime

with open('config/config.json', 'r', encoding='utf-8-sig') as f:
    cfg = json.load(f)
log_file = cfg.get('log_file', 'logs/bot_logs.xlsx')


def log_action(action_type: str, message: str, source_channel: str):
    try:
        df = pd.read_excel(log_file)
    except FileNotFoundError:
        df = pd.DataFrame(columns=['Время', 'Тип', 'Канал', 'Сообщение'])
    new_row = {
        'Время': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Тип': action_type,
        'Канал': source_channel,
        'Сообщение': message
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(log_file, index=False)


def log_error(error: str):
    log_action('ERROR', error, 'SYSTEM')