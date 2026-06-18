"""Bidirectional BG <-> EN product search via a Latin phonetic skeleton.

Both the search query and the product names are reduced to the same Latin
"skeleton", so a Cyrillic query matches Latin-named products and vice-versa.
Phonetic collapses (c->k, qu->kv, x->ks, w->v, y->i) bridge the common
spelling gaps (Coca<->кока, Nesquik<->несквик, Olympus<->олимпус).
"""
from __future__ import annotations

import re

# Official Bulgarian romanisation (lossy on purpose; we normalise both sides).
_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a",
    "ь": "y", "ю": "yu", "я": "ya",
}


def to_latin(s: str) -> str:
    s = s.lower()
    return "".join(_CYR2LAT.get(ch, ch) for ch in s)


def search_key(s: str) -> str:
    """Latin phonetic skeleton used for cross-script substring matching."""
    s = to_latin(s)
    s = s.replace("ch", "\x01")   # protect digraph from the c->k rule
    s = s.replace("qu", "kv")
    s = s.replace("x", "ks")
    s = s.replace("w", "v")
    s = s.replace("y", "i")
    s = s.replace("c", "k")
    s = s.replace("\x01", "ch")
    s = re.sub(r"[^a-z0-9]+", " ", s)   # drop punctuation
    s = re.sub(r"(.)\1+", r"\1", s)      # collapse repeated chars
    return re.sub(r"\s+", " ", s).strip()
