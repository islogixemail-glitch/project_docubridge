# app.py — Flask-сервер и точка входа для Telegram webhook

import traceback
import json
from flask import request

from config import app, bot, WEBHOOK_BASE, WEBHOOK_SECRET, PORT
from telebot.types import Update
from db import init_db_pool, ensure_tables, is_update_processed, mark_update_processed


@app.route("/", methods=["GET"])
def index():
    return "OK", 200


@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def telegram_webhook():
    try:
        if request.headers.get("content-type") == "application/json":
            json_data = json.loads(request.data.decode("utf-8"))
            update = Update.de_json(json_data)
            update_id = update.update_id
            print(f"[Webhook] Получено обновление: {update_id}")

            if is_update_processed(update_id):
                print(f"[Webhook] Update {update_id} уже обработан, пропускаем")
                return "OK", 200

            mark_update_processed(update_id)
            bot.process_new_updates([update])
            print(f"[Webhook] Обновление {update_id} обработано")
        else:
            print("[Webhook] Unsupported content-type")
    except Exception as e:
        print("[Webhook] Ошибка обработки:", e)
        traceback.print_exc()
    return "OK", 200


def ensure_webhook():
    if not WEBHOOK_BASE:
        print("❌ ERROR: WEBHOOK_BASE не задан — бот не будет работать!")
        raise SystemExit(1)

    url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
    bot.remove_webhook()
    ok = bot.set_webhook(url=url, drop_pending_updates=True)
    if ok:
        print(f"✅ Webhook установлен: {url}")
    else:
        print("❌ ERROR: Не удалось установить webhook")
        raise SystemExit(1)


# --------------------
# Запуск приложения
# --------------------
if __name__ == "__main__":
    init_db_pool()
    ensure_tables()
    ensure_webhook()
    app.run(host="0.0.0.0", port=PORT, debug=False)
