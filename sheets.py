"""
Запись заявок в Google Таблицу через Google Apps Script.
Google Cloud не нужен: в таблицу вставляется маленький скрипт (apps_script.gs),
бот отправляет ему данные по ссылке.

Проверить подключение без Telegram: python sheets.py
"""
import os

import requests
from dotenv import load_dotenv

from config import COLUMNS

load_dotenv()
WEB_APP_URL = os.getenv('WEB_APP_URL')
SECRET = os.getenv('SECRET')
SHEET_URL = os.getenv('SHEET_URL', '')


def _safe(value):
    """Текст, начинающийся с = + - @, таблица считает формулой.
    Апостроф в начале говорит: «это просто текст» (в ячейке он не виден)."""
    value = str(value)
    if value[:1] in ('=', '+', '-', '@'):
        return "'" + value
    return value


def add_row(values):
    """Отправляет строку в таблицу. При ошибке выбрасывает исключение."""
    if not WEB_APP_URL or not SECRET:
        raise RuntimeError('В .env не заполнены WEB_APP_URL или SECRET')
    payload = {'secret': SECRET, 'columns': COLUMNS, 'row': [_safe(v) for v in values]}
    response = requests.post(WEB_APP_URL, json=payload, timeout=20)
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError('Скрипт вернул не JSON. Проверьте, что доступ открыт для «Все»')
    if not result.get('ok'):
        raise RuntimeError(f'Скрипт ответил ошибкой: {result.get("error")}')


def check_settings():
    """Быстрая проверка настроек при запуске бота (без записи в таблицу)."""
    if not WEB_APP_URL or not SECRET:
        raise RuntimeError('В .env не заполнены WEB_APP_URL или SECRET')


def sheet_url():
    return SHEET_URL or '(ссылка на таблицу не указана в .env)'


if __name__ == '__main__':
    from datetime import datetime
    print('Отправляю тестовую строку...')
    add_row([datetime.now().strftime('%d.%m.%Y %H:%M'), 'Тест', '+7 900 000-00-00',
             'Проверка', 'Строка из sheets.py', '', 'Тест'])
    print('Готово! Откройте таблицу — там должна появиться строка «Тест».')
