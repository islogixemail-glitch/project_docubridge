# messages.py — генерация UI-элементов и уведомлений администратору

from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from typing import Dict

from config import bot, ADMIN_CHAT_ID
from constants import PRICING
from form_logic import compute_quote  # imported here to avoid circular import


def main_menu() -> ReplyKeyboardMarkup:
    """Клавиатура главного меню."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("/consult"))
    kb.add(KeyboardButton("/reset"))
    kb.add(KeyboardButton("/news"))
    return kb


def notify_admin_lead(source_chat_id: int, payload: Dict):
    """Отправляет карточку лида администратору."""
    if not ADMIN_CHAT_ID:
        print("[ADMIN] ADMIN_CHAT_ID не задан — уведомление не отправлено")
        return
    if ADMIN_CHAT_ID == source_chat_id:
        print("[ADMIN] Уведомление пропущено (тестовый режим)")
        return

    try:
        q = compute_quote(payload)
        price_line = f"Оценка: €{q['price_eur']} (до {q['threshold_g']} г)" if q["price_eur"] is not None else "Оценка: по согласованию"
        eta_line = f"Срок: ориентировочно {q['eta_working']} рабочих дней" if q.get("eta_working") else "Срок: требует уточнения"
        note_line = f"Примечание: {q['notes']}" if q.get("notes") else None

        lines = [
            "🟢 *Новый лид (DocuBridge)*",
            f"Chat ID: `{source_chat_id}`",
            "",
            f"Тип документа: {payload.get('doc_type', '—')}",
            f"Маршрут: {payload.get('from_country')}/{payload.get('from_city')} → {payload.get('to_country')}/{payload.get('to_city')}",
            f"Листов A4: {payload.get('pages_a4', 0)}, вес ≈ {payload.get('weight_grams', 0)} г",
            f"Срочность: {payload.get('urgency', '—')}",
            "",
            price_line,
            eta_line,
        ]
        if note_line:
            lines.append(note_line)
        lines += [
            "",
            f"Имя: {payload.get('name', '—')}",
            f"Телефон: {payload.get('phone', '—')}",
            f"Email: {payload.get('email', '—')}",
            f"Лучшее время связи: {payload.get('best_time', '—')}",
        ]

        bot.send_message(ADMIN_CHAT_ID, "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        print(f"[ADMIN notify] Ошибка при отправке уведомления: {e}")
