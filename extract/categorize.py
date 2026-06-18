"""Heuristic brand & category guessing for Kaufland product names.

Receipts print neither brand nor category, so these are *guesses* meant as a
starting point — the user corrects them in data/product_meta.csv. Names are
Bulgarian (Cyrillic), heavily abbreviated, ~18 chars.
"""
from __future__ import annotations

import re

# --- known brands (Cyrillic + Latin, lowercase substrings) -------------------
# Matched as case-insensitive substrings of the product name.
BRANDS = [
    "olympus", "devin", "perrier", "san pellegrino", "schweppes", "coca cola",
    "coca", "cappy", "pfanner", "florina", "velinградgrad", "велинград",
    "михалково", "пелистерка", "горна баня", "банкя",
    "barni", "milka", "kinder", "lindt", "ferrero", "raffaelo", "rocher",
    "chio", "pom bar", "kroki", "кроки", "salza", "wolf", "ricola", "troya",
    "троя", "boровец", "боровец", "caprice", "rois",
    "активиа", "activia", "danone", "arla", "president", "weid", "weihenste",
    "балкан", "верея", "ведраре", "боженци", "елена", "саяна", "маджаров",
    "домлян", "olympus", "k-bio", "k-fav", "klc", "klc", "krina", "крина",
    "qualita", "lavazza", "jacobs", "nescafe", "нескафе", "costa",
    "колос", "златна добруджа", "добруджа", "житен дар", "силует",
    "amadori", "carrefour", "cr", "брей", "bevola", "bochko", "бочко", "бебо",
    "domestos", "somat", "colgate", "dove", "safeguard", "aquafresh", "vileda",
    "zewa", "zebra", "papia", "emeka", "емека", "fino", "unicart", "joli",
    "pampers", "hipp", "agiva", "aile", "bic", "varta", "vitamin aqua",
    "calиakra", "калиакра", "kaufland", "кауфланд", "yopro", "yo pro",
    "коко", "k-classic", "k classic", "sole mio", "karmela", "кристал",
    "olympus", "pelican", "пеликан", "лудогорие", "родопея", "ботевградско",
]

# --- category rules: ordered (more specific first); first match wins ---------
# Each rule: (category, [keyword substrings, lowercase]).
CATEGORY_RULES = [
    ("Яйца", ["яйц", "яйца"]),
    ("Сирене и кашкавал", ["кашкавал", "кашк", "каш.", "сирене", "извара",
                            "моцарела", "пармезан", "крем сирене", "кр.сирене",
                            "фета", "гауда", "крема"]),
    ("Мляко и млечни", ["прясно мляко", " пм", "пм ", "кисело", " км", "км ",
                          "мляко", "кефир", "айран", "йогурт", "цедено",
                          "сметана", "масло", "извара", "млеч"]),
    ("Месо и колбаси", ["пиле", "пилеш", "свинск", "телешк", "кайма", "мляно",
                         "месо", "луканка", "шунка", "салам", "кабаноси",
                         "бекон", "наденица", "пастърма", "прошуто", "саздърма",
                         "плешка", "филе", "бут", "стек", "сърлоин", "заек",
                         "пиле", "пуйка", "скариди", "риба", "сьомга"]),
    ("Хляб и тестени", ["хляб", "багета", "питка", "кроасан", "земел",
                         "пърленка", "симид", "милинка", "донът", "поничка",
                         "закуска", "банич", "козунак", "коледниче", "бутерка",
                         "крем", "паста микс", "сухар"]),
    ("Плодове и зеленчуци", ["банан", "ябълк", "домат", "краставиц", "лук",
                              "морков", "картоф", "чушк", "лимон", "киви",
                              "ягод", "боровинк", "малин", "авокадо", "зеле",
                              "тиквичк", "чери", "грозде", "круш", "портокал",
                              "пъпеш", "диня", "праскул", "праскова", "пипер",
                              "магданоз", "копър", "маруля", "репичк", "ряпа",
                              "грах", "спанак", "салат", "гъби", "ананас",
                              "боб", "леща", "корен", "пащърнак", "дайкон",
                              "сладки", "цвекло", "маслини", "фурми", "ягоди"]),
    ("Вода", ["вода", "минерал", "изворна", "газ вода", "ест.газ"]),
    ("Напитки", ["cola", "кола", "fanta", "фанта", "schweppes", "швепс", "сок",
                  "нектар", "cappy", "pfanner", "лимонада", "pepsi", "пепси",
                  "энергийна", "айс ти", "ice tea", "fuzetea"]),
    ("Кафе и чай", ["кафе", "nescafe", "нескафе", "lavazza", "jacobs", "costa",
                     "чай", "лайка", "nespresso", "капсул", "пури"]),
    ("Захарни и снакс", ["шоколад", "бонбон", "вафла", "вафл", "бисквит",
                          "barni", "milka", "kinder", "lindt", "ferrero",
                          "raffaelo", "rocher", "чипс", "снакс", "солет",
                          "гризини", "stickletti", "pom bar", "кроки",
                          "пуканки", "крекер", "десерт", "кекс", "торта",
                          "кашу", "лешник", "ядки", "бар"]),
    ("Основни храни", ["олио", "брашно", "ориз", "нишесте", "захар", "макарон",
                        "паста", "грис", "спагети", "юфка", "майонеза",
                        "кетчуп", "горчица", "конфитюр", "мед", "оцет",
                        "подправк", "сол", "бакпулвер", "боя за", "пудинг"]),
    ("Бебешко", ["hipp", "бебе", "пюре", "бебешк", "pampers", "памперс"]),
    ("Хигиена и козметика", ["паста зъби", "четка зъби", "сапун", "шампоан",
                              "душ гел", "дезодорант", "крем", "colgate",
                              "dove", "safeguard", "aquafresh", "клечки",
                              "кърпич", "тоал", "носни", "agiva"]),
    ("Дом и бит", ["торбичка", "торба", "салфетк", "хартия", "ролк", "домест",
                    "somat", "препарат", "гъба", "батери", "запалка", "свещ",
                    "фолио", "торби", "кутия", "чаша", "кърпа", "мебел",
                    "възглавница", "магнит", "картичка", "книжка", "кн.",
                    "играчк", "чорапи", "vileda", "zebra", "papia", "emeka"]),
]

_FIRST_TOKEN = re.compile(r"^[^\s.,]+")


def _norm(s: str) -> str:
    return s.lower().replace("ё", "е")


def guess_brand(name: str) -> str:
    low = _norm(name)
    for b in BRANDS:
        if b in low:
            # Return a tidy display form: capitalised first letter of the match.
            return b.upper() if len(b) <= 3 else b[:1].upper() + b[1:]
    # Fallback: a capitalised first token that isn't a generic noun.
    m = _FIRST_TOKEN.match(name.strip())
    if m:
        tok = m.group(0)
        if tok[:1].isupper() and not _is_generic(tok):
            return tok
    return ""


def guess_category(name: str) -> str:
    low = _norm(name)
    for category, keywords in CATEGORY_RULES:
        if any(k in low for k in keywords):
            return category
    return ""


# Generic leading words that are categories/units, not brands.
_GENERIC = {
    "хляб", "мляко", "сирене", "кашкавал", "вода", "яйца", "банани", "домати",
    "краставици", "картофи", "лук", "морков", "моркови", "ягоди", "пиле",
    "свинско", "телешко", "месо", "кайма", "сок", "чай", "кафе", "захар",
    "брашно", "олио", "ориз", "торбичка", "торба", "салфетки", "хартия",
    "кроасан", "багета", "питка", "крем", "паста", "майонеза", "масло",
    "боровинки", "малини", "гъби", "чушки", "лимони", "круши", "ябълки",
    "био", "кн", "ус", "кайма", "мляно", "хляб", "хлябгорублянски",
    "земел", "донът", "ягоди", "малини", "ананас", "заек", "авокадо",
    "немска", "пражка", "прошуто", "саздърма", "телешко",
}


def _is_generic(token: str) -> bool:
    return _norm(token).strip(".,") in _GENERIC
