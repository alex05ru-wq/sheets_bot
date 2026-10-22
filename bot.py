"""
Telegram-бот для приёма заявок: каждая заявка сразу
появляется новой строкой в Google Таблице, владелец получает уведомление.

Запуск: python bot.py   (перед этим заполните .env и credentials.json)
"""
import csv
import os
import threading
from datetime import datetime
from html import escape
from pathlib import Path

import telebot
from dotenv import load_dotenv
from telebot import types

import sheets
from config import BUSINESS_NAME, NEW_STATUS, SERVICES

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')
if not TOKEN:
    raise SystemExit('Не найден BOT_TOKEN. Создайте файл .env (см. .env.example)')

BACKUP_FILE = Path(__file__).parent / 'заявки_резерв.csv'
BTN_REQUEST = '📝 Оставить заявку'
BTN_CANCEL = '❌ Отмена'
BTN_SKIP = 'Пропустить'

bot = telebot.TeleBot(TOKEN)

# user_id -> {'step': ..., 'name': ..., 'phone': ..., 'service': ..., 'comment': ...}
sessions = {}
lock = threading.Lock()


# ---------- Клавиатуры ----------

def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(BTN_REQUEST)
    return kb


def cancel_keyboard(*extra):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for button in extra:
        kb.add(button)
    kb.add(BTN_CANCEL)
    return kb


def phone_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton('📱 Отправить мой номер', request_contact=True))
    kb.add(BTN_CANCEL)
    return kb


def services_keyboard():
    kb = types.InlineKeyboardMarkup()
    for i, name in enumerate(SERVICES):
        kb.add(types.InlineKeyboardButton(name, callback_data=f'srv:{i}'))
    return kb


def confirm_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton('✅ Отправить заявку', callback_data='send'))
    kb.add(types.InlineKeyboardButton('🔄 Заполнить заново', callback_data='again'),
           types.InlineKeyboardButton('❌ Отмена', callback_data='cancel'))
    return kb


# ---------- Вспомогательное ----------

def get_session(user_id):
    with lock:
        return sessions.get(user_id)


def set_step(user_id, step, **data):
    with lock:
        s = sessions.setdefault(user_id, {})
        s.update(data)
        s['step'] = step


def clear(user_id):
    with lock:
        sessions.pop(user_id, None)


def format_phone(text):
    """Приводит номер к виду +7 900 123-45-67. Если номер не похож на российский — None."""
    digits = ''.join(ch for ch in text if ch.isdigit())
    if len(digits) == 10:
        digits = '7' + digits
    elif len(digits) == 11 and digits[0] == '8':
        digits = '7' + digits[1:]
    if len(digits) != 11 or digits[0] != '7':
        return None
    d = digits
    return f'+7 {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:11]}'


def save_backup(row):
    """Если Google Таблица недоступна — заявка не теряется, а пишется в CSV."""
    new_file = not BACKUP_FILE.exists()
    with open(BACKUP_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        if new_file:
            from config import COLUMNS
            writer.writerow(COLUMNS)
        writer.writerow(row)


def notify_admin(text):
    if not ADMIN_ID:
        return
    try:
        bot.send_message(ADMIN_ID, text, parse_mode='HTML')
    except Exception as e:
        print('Не удалось уведомить владельца:', e)


# ---------- Шаги анкеты ----------

def start_form(chat_id, user_id):
    set_step(user_id, 'name')
    bot.send_message(chat_id, 'Как к вам обращаться? Напишите имя:',
                     reply_markup=cancel_keyboard())


def ask_phone(chat_id):
    bot.send_message(chat_id, 'Ваш номер телефона? Нажмите кнопку ниже или напишите номер:',
                     reply_markup=phone_keyboard())


def ask_service(chat_id):
    bot.send_message(chat_id, 'Какая услуга нужна?', reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(chat_id, 'Выберите из списка 👇', reply_markup=services_keyboard())


def ask_comment(chat_id):
    bot.send_message(chat_id, 'Опишите задачу или удобное время для звонка.\n'
                              'Если нечего добавить — нажмите «Пропустить».',
                     reply_markup=cancel_keyboard(BTN_SKIP))


def show_summary(chat_id, user_id):
    s = get_session(user_id)
    text = ('<b>Проверьте заявку:</b>\n\n'
            f'Имя: <b>{escape(s["name"])}</b>\n'
            f'Телефон: <b>{escape(s["phone"])}</b>\n'
            f'Услуга: <b>{escape(s["service"])}</b>\n'
            f'Комментарий: {escape(s["comment"]) or "—"}')
    bot.send_message(chat_id, '✅ Почти готово', reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=confirm_keyboard())


# ---------- Команды ----------

@bot.message_handler(commands=['start'])
def cmd_start(message):
    clear(message.from_user.id)
    bot.send_message(message.chat.id,
                     f'Здравствуйте! Это бот компании {BUSINESS_NAME}.\n\n'
                     'Оставьте заявку — мы перезвоним в ближайшее время.',
                     reply_markup=main_keyboard())


@bot.message_handler(commands=['myid'])
def cmd_myid(message):
    bot.send_message(message.chat.id, f'Ваш ID: {message.from_user.id}')


@bot.message_handler(commands=['table'])
def cmd_table(message):
    """Ссылка на таблицу — только для владельца."""
    if str(message.from_user.id) == str(ADMIN_ID):
        bot.send_message(message.chat.id, f'📊 Таблица заявок:\n{sheets.sheet_url()}')


# ---------- Кнопки под сообщениями ----------

@bot.callback_query_handler(func=lambda c: c.data.startswith('srv:'))
def on_service(call):
    bot.answer_callback_query(call.id)
    s = get_session(call.from_user.id)
    if not s or s.get('step') != 'service':
        return
    index = int(call.data.split(':')[1])
    if not 0 <= index < len(SERVICES):
        return
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, f'Услуга: {SERVICES[index]}')
    set_step(call.from_user.id, 'comment', service=SERVICES[index])
    ask_comment(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data in ('send', 'again', 'cancel'))
def on_confirm(call):
    bot.answer_callback_query(call.id)
    chat_id, user = call.message.chat.id, call.from_user
    s = get_session(user.id)
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    if not s or s.get('step') != 'confirm':
        bot.send_message(chat_id, 'Заявка устарела, начните заново.', reply_markup=main_keyboard())
        return
    if call.data == 'cancel':
        clear(user.id)
        bot.send_message(chat_id, 'Заявка отменена.', reply_markup=main_keyboard())
        return
    if call.data == 'again':
        start_form(chat_id, user.id)
        return

    # call.data == 'send'
    username = f'@{user.username}' if user.username else f'id {user.id}'
    row = [datetime.now().strftime('%d.%m.%Y %H:%M'), s['name'], s['phone'],
           s['service'], s['comment'], username, NEW_STATUS]
    try:
        sheets.add_row(row)
        saved_to = 'таблицу'
    except Exception as e:
        print('Ошибка записи в Google Таблицу:', e)
        save_backup(row)
        saved_to = 'резервный файл (таблица недоступна!)'
    clear(user.id)

    bot.send_message(chat_id, '🎉 Спасибо! Заявка принята, мы скоро свяжемся с вами.',
                     reply_markup=main_keyboard())
    notify_admin('📥 <b>Новая заявка</b>\n\n'
                 f'Имя: {escape(row[1])}\nТелефон: {escape(row[2])}\n'
                 f'Услуга: {escape(row[3])}\nКомментарий: {escape(row[4]) or "—"}\n'
                 f'Telegram: {escape(username)}\n\nЗаписано в {saved_to}')


# ---------- Ответы пользователя ----------

@bot.message_handler(content_types=['contact'])
def on_contact(message):
    s = get_session(message.from_user.id)
    if s and s.get('step') == 'phone':
        phone = format_phone(message.contact.phone_number) or message.contact.phone_number
        set_step(message.from_user.id, 'service', phone=phone)
        ask_service(message.chat.id)


@bot.message_handler(content_types=['text'])
def on_text(message):
    chat_id, user_id, text = message.chat.id, message.from_user.id, message.text.strip()

    if text == BTN_CANCEL:
        clear(user_id)
        bot.send_message(chat_id, 'Отменено.', reply_markup=main_keyboard())
        return
    if text == BTN_REQUEST:
        start_form(chat_id, user_id)
        return

    s = get_session(user_id)
    step = s.get('step') if s else None

    if step == 'name':
        if not 1 < len(text) <= 50:
            bot.send_message(chat_id, 'Напишите имя (от 2 до 50 символов):')
            return
        set_step(user_id, 'phone', name=text)
        ask_phone(chat_id)
    elif step == 'phone':
        phone = format_phone(text)
        if not phone:
            bot.send_message(chat_id, '⚠️ Похоже, в номере ошибка. Пример: +7 900 123-45-67')
            return
        set_step(user_id, 'service', phone=phone)
        ask_service(chat_id)
    elif step == 'service':
        bot.send_message(chat_id, 'Выберите услугу кнопкой выше 👆')
    elif step == 'comment':
        comment = '' if text == BTN_SKIP else text[:500]
        set_step(user_id, 'confirm', comment=comment)
        show_summary(chat_id, user_id)
    elif step == 'confirm':
        bot.send_message(chat_id, 'Нажмите «Отправить заявку» под сводкой 👆')
    else:
        bot.send_message(chat_id, 'Нажмите кнопку, чтобы оставить заявку 👇',
                         reply_markup=main_keyboard())


if __name__ == '__main__':
    try:
        sheets.check_settings()
        print('Таблица:', sheets.sheet_url())
    except Exception as e:
        print('⚠️', e)
        print('Заявки будут сохраняться в', BACKUP_FILE.name)
    print('Бот запущен. Остановить: Ctrl+C')
    bot.infinity_polling(skip_pending=True)
