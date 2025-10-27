"""
ai.py — работа с OpenAI: генерация ответов, извлечение данных анкеты из свободного текста,
а также эвристические и вспомогательные методы.
"""

import json
import re
from typing import Optional, Dict, Any

from config import client

# ----------------------------
# Быстрый ответ от ИИ (не анкета)
# ----------------------------
def ai_reply(text: str) -> str:
    """Отвечает на произвольный текст пользователя с помощью OpenAI."""
    if not client:
        return "ИИ сейчас временно недоступен. Попробуйте позже."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты вежливый логист-ассистент DocuBridge. Отвечай кратко и по делу, на русском."},
                {"role": "user", "content": text},
            ],
            temperature=0.6,
            max_tokens=500,
            timeout=30,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[OpenAI] ai_reply error: {e}")
        return "Произошла ошибка на стороне ИИ. Попробуйте позже."


# ----------------------------
# Распознавание анкеты из свободного текста
# ----------------------------
AI_KEYS = {
    "doc_type", "from_country", "from_city", "to_country", "to_city",
    "pages_a4", "weight_grams", "urgency", "name", "phone", "email", "best_time"
}

def ai_understand(text: str) -> Optional[Dict[str, Any]]:
    """Пытается извлечь поля анкеты из текста пользователя с помощью GPT."""
    if not client:
        return None
    try:
        system_prompt = (
            "Ты логистический ассистент DocuBridge. "
            "Извлеки из текста анкеты поля: "
            "(doc_type, from_country, from_city, to_country, to_city, "
            "pages_a4, weight_grams, urgency, name, phone, email, best_time). "
            "Верни только JSON-объект без пояснений."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=400,
            timeout=30,
        )
        content = (response.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            return None
        return clean_ai_data(data)
    except Exception as e:
        print(f"[OpenAI] ai_understand error: {e}")
        return None


# ----------------------------
# Очистка и нормализация данных от GPT
# ----------------------------
def clean_ai_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Удаляет лишние поля, нормализует значения, проверяет типы."""
    from utils import valid_email, valid_phone, valid_name
    cleaned: Dict[str, Any] = {}

    for key, value in data.items():
        if key not in AI_KEYS or value is None:
            continue
        str_value = str(value).strip()

        if key in {"pages_a4", "weight_grams"}:
            try:
                iv = int(value)
                if iv >= 0:
                    cleaned[key] = iv
            except Exception:
                continue
        elif key in {"from_country", "to_country"}:
            nv = normalize_country(str_value)
            if nv:
                cleaned[key] = nv
        elif key == "urgency":
            nu = normalize_urgency(str_value)
            if nu:
                cleaned[key] = nu
        elif key == "phone":
            if valid_phone(str_value):
                cleaned[key] = str_value
        elif key == "email":
            if valid_email(str_value):
                cleaned[key] = str_value
        elif key == "name":
            if valid_name(str_value):
                cleaned[key] = str_value
        else:
            if str_value:
                cleaned[key] = str_value

    # автоподставляем вес по страницам
    if "pages_a4" in cleaned and "weight_grams" not in cleaned:
        pages = cleaned["pages_a4"]
        if isinstance(pages, int) and pages > 0:
            cleaned["weight_grams"] = pages * 6

    return cleaned


# ----------------------------
# Эвристики без GPT
# ----------------------------
URGENCY_SYNONYMS = {
    "срочная": [
        "срочно", "срочная", "экспресс", "быстро", "как можно быстрее", "ускоренная",
        "urgent", "express"
    ],
    "обычная": [
        "обычно", "обычная", "стандарт", "небыстро", "без спешки", "standard", "normal"
    ],
}

def infer_urgency(text: str) -> Optional[str]:
    """Пытается определить срочность доставки по ключевым словам."""
    s = text.lower()
    for label, words in URGENCY_SYNONYMS.items():
        for word in words:
            if word in s:
                return label
    return None

def heuristic_parse(text: str) -> Optional[Dict[str, Any]]:
    """Эвристическое извлечение информации из текста без GPT."""
    if not text:
        return None
    result = {}
    s = text.lower()

    # Срочность
    urgency = infer_urgency(s)
    if urgency:
        result["urgency"] = urgency

    # Вес
    m = re.search(r"(\d+)\s*(?:г|гр|грамм)", s)
    if m:
        result["weight_grams"] = int(m.group(1))

    # Страницы
    m = re.search(r"(\d+)\s*(?:лист|стр)", s)
    if m:
        result["pages_a4"] = int(m.group(1))

    # Автоматическая подстановка веса по страницам
    if "pages_a4" in result and "weight_grams" not in result:
        pages = result["pages_a4"]
        if pages > 0:
            result["weight_grams"] = pages * 6

    return result or None


# ----------------------------
# Нормализация стран и срочности
# ----------------------------
def normalize_country(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    mapping = {
        "украина": "Украина", "ukraine": "Украина", "ua": "Украина",
        "россия": "Россия", "rf": "Россия", "ru": "Россия", "russia": "Россия",
        "беларусь": "Беларусь", "рб": "Беларусь", "by": "Беларусь", "belarus": "Беларусь"
    }
    key = value.strip().lower()
    return mapping.get(key, value.strip().title())

def normalize_urgency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    s = value.strip().lower()
    if s in {"обычная", "standard", "normal"}:
        return "обычная"
    if s in {"срочная", "express", "urgent"}:
        return "срочная"
    return None
