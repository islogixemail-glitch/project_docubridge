"""
config.py — конфигурация проекта DocuBridge Bot
Содержит загрузку .env и глобальные параметры окружения
"""

import os
from dotenv import load_dotenv
from openai import OpenAI
import telebot
from flask import Flask

# ----------------------------
# Загрузка .env файла
# ----------------------------
load_dotenv()

# ----------------------------
# TELEGRAM / BOT
# ----------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ ERROR: TELEGRAM_BOT_TOKEN не задан в .env")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ----------------------------
# DATABASE
# ----------------------------
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("⚠️ WARNING: DATABASE_URL не задан — сохранение истории отключено")

# ----------------------------
# FLASK / WEBHOOK
# ----------------------------
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret-path")
PORT = int(os.getenv("PORT", "5000"))

app = Flask(__name__)

# ----------------------------
# ADMIN / SYSTEM
# ----------------------------
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
print(f"[ADMIN] Admin ID: {ADMIN_CHAT_ID or '— (не задан)'}")

# ----------------------------
# OPENAI
# ----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("[OpenAI] client: ON")
else:
    client = None
    print("[OpenAI] client: OFF")

# ----------------------------
# EXPORT
# ----------------------------
__all__ = [
    "bot",
    "app",
    "client",
    "BOT_TOKEN",
    "DB_URL",
    "WEBHOOK_BASE",
    "WEBHOOK_SECRET",
    "PORT",
    "ADMIN_CHAT_ID",
]
