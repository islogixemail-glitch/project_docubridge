# utils.py — валидация, парсинг чисел и извлечение значений из текста

import re
from typing import Optional

# --- Распознавание чисел словами (на русском) ---
RUS_NUMS = {
    "ноль": 0, "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
    "семьдесят": 70, "восемьдесят": 80, "девяносто": 90, "сто": 100
}

def parse_int(text: str) -> Optional[int]:
    if not text:
        return None
    s = text.strip().lower()
    m = re.search(r"\d+", s)
    if m:
        try:
            return int(m.group())
        except Exception:
            pass
    tokens = re.findall(r"[а-яё]+", s)
    total = 0
    last = 0
    seen = False
    for t in tokens:
        if t in RUS_NUMS:
            seen = True
            val = RUS_NUMS[t]
            if val >= 20 and val % 10 == 0:
                last = val
            else:
                if last:
                    total += last + val
                    last = 0
                else:
                    total += val
    if seen:
        return total if total > 0 else (last if last > 0 else None)
    return None

# --- Проверки валидности ---
def valid_email(s: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s.strip(), flags=re.I))

def valid_phone(s: str) -> bool:
    s = s.strip().replace(" ", "")
    return s.startswith("+380") or s.startswith("+7") or s.startswith("+375")

def valid_name(s: str) -> bool:
    s = s.strip()
    return bool(re.match(r"^[A-Za-zА-Яа-яЁё\-\s]{2,}$", s))


# --- Распознавание полей по синонимам ---
FIELD_ALIASES = {
    "doc_type":      ["тип документа", "документ", "вид документа"],
    "from_country":  ["страна отправки", "страна откуда", "из страны", "страна-отправитель"],
    "from_city":     ["город отправки", "город откуда", "из города"],
    "to_country":    ["страна доставки", "страна назначения", "в страну", "страна-получатель"],
    "to_city":       ["город доставки", "город назначения", "в город"],
    "pages_a4":      ["страницы", "страниц", "листов", "листы", "количество страниц", "а4"],
    "weight_grams":  ["вес", "масса", "грамм", "граммы"],
    "urgency":       ["срочность", "скорость", "режим доставки"],
    "name":          ["имя", "фамилия", "как обращаться"],
    "phone":         ["телефон", "номер", "контакт"],
    "email":         ["почта", "email", "электронная почта"],
    "best_time":     ["время связи", "связаться", "лучшее время"],
}

def alias_to_key(text: str) -> Optional[str]:
    s = (text or "").lower()
    for key, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in s:
                return key
    return None
