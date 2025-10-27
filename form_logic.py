# form_logic.py — основная логика анкетирования, валидации и обработки ответов

from typing import Dict, Optional
from telebot.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from db import get_state, set_state, update_data, save_message, insert_lead
from ai import ai_reply, heuristic_parse, ai_understand, infer_urgency
from utils import parse_int, valid_email, valid_phone, valid_name

from config import bot, ADMIN_CHAT_ID
from messages import main_menu, notify_admin_lead
from constants import FIELDS, COUNTRY_CHOICES, PRICING

# --- Основной обработчик сообщений (от пользователя) ---
def handle_answer(chat_id: int, text: str):
    print(f"[Wizard] handle_answer: chat_id={chat_id}, text='{text}'")

    state, data = get_state(chat_id)
    save_message(chat_id, text, None)

    # AI-парсинг вне визарда
    if state != "collecting":
        parsed = heuristic_parse(text) or ai_understand(text)
        if parsed:
            print(f"[Wizard] AI Parsed intent: {parsed}")
            data = merge_ai_data({}, parsed)
            idx = first_missing_index(data)
            if idx >= len(FIELDS):
                return finalize_form(chat_id, data)
            data["_idx"] = idx
            set_state(chat_id, "collecting", data)
            bot.send_message(chat_id, "Понял вас. Давайте уточним пару моментов.", reply_markup=ReplyKeyboardRemove())
            ask(chat_id, idx, data)
            return

        reply = ai_reply(text)
        save_message(chat_id, text, reply)
        bot.send_message(chat_id, reply, reply_markup=main_menu())
        return

    # Визард продолжается
    data = data or {}
    idx = int(data.get("_idx", 0))
    if idx < 0 or idx >= len(FIELDS):
        idx = 0
    field = FIELDS[idx]
    key = field["key"]
    t = field["type"]
    val = None
    err = None
    s = text.strip()

    if t == "text":
        val = s if len(s) >= 1 else None
        if not val:
            err = "Пустое значение. Повторите, пожалуйста."
    elif t == "choice":
        norm_map = {str(c).lower(): c for c in field["choices"]}
        s_norm = s.lower()
        if key == "urgency":
            syn = infer_urgency(s)
            if syn:
                s_norm = syn
        if s_norm in norm_map:
            val = norm_map[s_norm]
        else:
            err = f"Выберите из: {', '.join(field['choices'])}"
    elif t == "int":
        n = parse_int(s)
        if n and n > 0:
            val = n
        else:
            err = "Введите число больше 0. Например: 5"
    elif t == "int_opt":
        if s.lower() in {"нет", "не знаю", "-"}:
            val = 0
        else:
            n = parse_int(s)
            if n is None or n < 0:
                err = "Укажите число или «нет»"
            else:
                val = n
    elif t == "phone":
        if valid_phone(s):
            val = s
        else:
            err = "Телефон должен начинаться с +380 / +7 / +375"
    elif t == "email":
        if valid_email(s):
            val = s
        else:
            err = "Некорректный email. Пример: test@example.com"
    elif t == "name":
        if valid_name(s):
            val = s
        else:
            err = "Введите имя или фамилию (не короче 2 символов)."

    if err:
        save_message(chat_id, None, err)
        bot.send_message(chat_id, err)
        ask(chat_id, idx, data)
        return

    data[key] = val
    if key == "pages_a4" and data.get("weight_grams") in (None, 0):
        data["weight_grams"] = int(val) * 6

    idx += 1
    if idx < len(FIELDS):
        data["_idx"] = idx
        update_data(chat_id, data)
        bot.send_message(chat_id, "Принято.", reply_markup=ReplyKeyboardRemove())
        ask(chat_id, idx, data)
        return

    finalize_form(chat_id, data)

def ask(chat_id: int, idx: int, data: Dict):
    field = FIELDS[idx]
    q = field["q"]
    kb = None

    if field["type"] == "choice":
        q += f" [{', '.join(field['choices'])}]"
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        row = []
        for choice in field["choices"]:
            row.append(KeyboardButton(choice))
            if len(row) >= 3:
                kb.add(*row)
                row = []
        if row:
            kb.add(*row)

    save_message(chat_id, None, q)
    bot.send_message(chat_id, q, reply_markup=kb or None)

def finalize_form(chat_id: int, data: Dict):
    insert_lead(chat_id, data)
    quote = compute_quote(data)

    price_line = f"Стоимость: €{quote['price_eur']} (до {quote['threshold_g']} г)" if quote["price_eur"] else "Стоимость: по согласованию"
    eta_line = f"Срок: {quote['eta_working']} рабочих дней" if quote["eta_working"] else "Срок: требует уточнения"
    summary = (
        f"✅ Спасибо! Все данные получены.
"
        f"{price_line}
{eta_line}
"
        f"Контакт: {data.get('name')}, {data.get('phone')}, {data.get('email')}

"
        f"Ожидайте — специалист скоро свяжется с вами."
    )

    notify_admin_lead(chat_id, data)
    save_message(chat_id, "", summary)
    bot.send_message(chat_id, summary, reply_markup=main_menu())
    set_state(chat_id, "completed")

def compute_quote(data: Dict) -> Dict:
    from_country = (data.get("from_country") or "").title()
    to_country = (data.get("to_country") or "").title()
    weight = int(data.get("weight_grams") or 0)
    urgency = (data.get("urgency") or "обычная").lower()

    tariff = PRICING.get(urgency, [])
    for max_w, price in tariff:
        if weight <= max_w:
            return {
                "price_eur": price,
                "threshold_g": max_w,
                "eta_working": eta_working_days(from_country, to_country),
                "notes": "ускоренная доставка" if urgency == "срочная" else None
            }
    return {
        "price_eur": None,
        "threshold_g": None,
        "eta_working": eta_working_days(from_country, to_country),
        "notes": "вес 0 г или >100 г — стоимость по согласованию"
    }

def eta_working_days(from_country: str, to_country: str) -> Optional[str]:
    if from_country == "Украина" and to_country == "Россия":
        return "27–29"
    if from_country == "Украина" and to_country == "Беларусь":
        return "21–23"
    if from_country in {"Россия", "Беларусь"} and to_country == "Украина":
        return None
    return None

def merge_ai_data(existing: Dict, parsed: Dict) -> Dict:
    merged = dict(existing or {})
    for k, v in parsed.items():
        if k not in merged or merged.get(k) in ("", None, 0):
            merged[k] = v
    if merged.get("pages_a4") and not merged.get("weight_grams"):
        merged["weight_grams"] = int(merged["pages_a4"]) * 6
    return merged

def first_missing_index(data: Dict) -> int:
    for i, field in enumerate(FIELDS):
        val = data.get(field["key"])
        if not is_field_filled(field["type"], val, field.get("choices")):
            return i
    return len(FIELDS)

def is_field_filled(t: str, val: Optional[str], choices=None) -> bool:
    if val is None:
        return False
    if t == "text":
        return bool(str(val).strip())
    if t == "choice":
        return str(val).strip() in choices
    if t == "int":
        try:
            return int(val) > 0
        except:
            return False
    if t == "int_opt":
        try:
            return int(val) >= 0
        except:
            return False
    if t == "phone":
        return valid_phone(str(val))
    if t == "email":
        return valid_email(str(val))
    if t == "name":
        return valid_name(str(val))
    return False
