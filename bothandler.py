
# bothadler.py — команды и обработка входящих сообщений Telegram

from telebot.types import Message

from config import bot
from db import set_state, save_message
from form_logic import handle_answer, ask
from messages import main_menu


@bot.message_handler(commands=['start'])
def cmd_start(message: Message):
    msg = (
        "Добро пожаловать в IS-Logix DocuBridge! 🇸🇰📄\n"
        "Нажмите /consult чтобы начать оформление заявки.\n"
        "Либо опишите задачу — я постараюсь заполнить анкету автоматически."
    )
    save_message(message.chat.id, "/start", msg)
    bot.send_message(message.chat.id, msg, reply_markup=main_menu())


@bot.message_handler(commands=['consult'])
def cmd_consult(message: Message):
    data = {"_idx": 0}
    set_state(message.chat.id, "collecting", data)
    ask(message.chat.id, 0, data)


@bot.message_handler(commands=['reset'])
def cmd_reset(message: Message):
    set_state(message.chat.id, "greeting", {})
    msg = "Сбросил сессию. Нажмите /consult чтобы начать заново."
    save_message(message.chat.id, "/reset", msg)
    bot.send_message(message.chat.id, msg, reply_markup=main_menu())


@bot.message_handler(commands=['news'])
def cmd_news(message: Message):
    msg = (
        "Новости DocuBridge: https://t.me/DocuBridgeInfo\n"
        "Готов помочь с вашим кейсом — /consult."
    )
    save_message(message.chat.id, "/news", msg)
    bot.send_message(message.chat.id, msg, reply_markup=main_menu())


@bot.message_handler(commands=['ai'])
def cmd_ai(message: Message):
    from ai import ai_reply
    reply = ai_reply("Ответь одним словом: OK")
    save_message(message.chat.id, "/ai", reply)
    bot.send_message(message.chat.id, f"AI: {reply}")


@bot.message_handler(func=lambda m: True)
def handle_text(message: Message):
    handle_answer(message.chat.id, message.text)
