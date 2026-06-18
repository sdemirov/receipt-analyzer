"""Group truncated/abbreviated product names into canonical products.

Kaufland prints item names truncated to ~18 chars, so the same product can
appear with small spelling/spacing differences across receipts. We:

1. Normalize each raw name (lowercase, split glued digits, drop punctuation).
2. Greedily cluster names whose normalized forms are similar enough
   (rapidfuzz ``token_set_ratio`` >= FUZZY_THRESHOLD).
3. Persist a ``raw_name, canonical_name, product_id`` mapping CSV.

The CSV is the editable source of truth: on re-runs, existing rows are kept
verbatim (so manual corrections survive) and only newly-seen raw names are
added — matched against existing canonicals first, else placed in new clusters.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from rapidfuzz import fuzz, process

from config import FUZZY_THRESHOLD, MAPPING_CSV

_LETTER_DIGIT = re.compile(r"(?<=[^\W\d_])(?=\d)", re.UNICODE)
_DIGIT_LETTER = re.compile(r"(?<=\d)(?=[^\W\d_])", re.UNICODE)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# Size/quantity tokens that distinguish otherwise-similar products
# (volume, weight, fat %, pack count). Units are canonicalised so that
# spelling variants of the same size match (e.g. "400г" == "400гр").
_SIZE_TOKEN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(мл|ml|кг|kg|гр|г|g|л|l|бр|%)", re.IGNORECASE)
_UNIT_CANON = {"ml": "мл", "l": "л", "g": "г", "гр": "г", "kg": "кг"}


def size_signature(raw: str) -> frozenset[str]:
    """Set of canonical size tokens in a name, e.g. {'1.5л', '3.7%'}."""
    sig = set()
    for num, unit in _SIZE_TOKEN.findall(raw.lower()):
        u = _UNIT_CANON.get(unit.lower(), unit.lower())
        sig.add(f"{float(num.replace(',', '.')):g}{u}")
    return frozenset(sig)


def normalize_name(raw: str) -> str:
    """Return a normalized key used for fuzzy comparison (not for display)."""
    s = raw.lower().replace(".", " ")
    s = _LETTER_DIGIT.sub(" ", s)
    s = _DIGIT_LETTER.sub(" ", s)
    s = _NON_WORD.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _clean_display(raw: str) -> str:
    return _WS.sub(" ", raw).strip()


def build_mapping(
    raw_names: Iterable[str],
    existing: Dict[str, Tuple[str, int]] | None = None,
) -> Dict[str, Tuple[str, int]]:
    """Build ``raw_name -> (canonical_name, product_id)``.

    ``existing`` rows are preserved unchanged. New raw names are matched against
    existing canonicals (via normalized form) when possible, otherwise greedily
    clustered among themselves.
    """
    existing = dict(existing or {})
    counts = Counter(raw_names)

    # Map normalized canonical -> (canonical_name, product_id) from existing rows.
    canon_by_norm: Dict[str, Tuple[str, int]] = {}
    max_id = 0
    for canonical, pid in existing.values():
        canon_by_norm.setdefault(normalize_name(canonical), (canonical, pid))
        max_id = max(max_id, pid)

    mapping: Dict[str, Tuple[str, int]] = dict(existing)
    new_names = [n for n in counts if n not in mapping]

    # Try to attach each new name to an existing canonical first. Reject the
    # fuzzy match if the two names have different, non-empty size signatures
    # (e.g. 1л vs 1,5л) so different package sizes stay separate products.
    norm_keys = list(canon_by_norm.keys())
    still_new: List[str] = []
    for name in new_names:
        norm = normalize_name(name)
        match = process.extractOne(norm, norm_keys, scorer=fuzz.token_set_ratio)
        if match and match[1] >= FUZZY_THRESHOLD:
            canonical = canon_by_norm[match[0]][0]
            sa, sb = size_signature(name), size_signature(canonical)
            if sa and sb and sa != sb:
                still_new.append(name)
            else:
                mapping[name] = canon_by_norm[match[0]]
        else:
            still_new.append(name)

    # Greedily cluster the remaining new names among themselves.
    # Process most frequent first so the canonical is the common spelling.
    # Each cluster locks onto the first non-empty size it sees; a name with a
    # different non-empty size cannot join (it starts its own cluster instead).
    still_new.sort(key=lambda n: (-counts[n], n))
    clusters: List[dict] = []  # {norm, size, members}
    for name in still_new:
        norm = normalize_name(name)
        sig = size_signature(name)
        placed = False
        for cl in clusters:
            if fuzz.token_set_ratio(norm, cl["norm"]) < FUZZY_THRESHOLD:
                continue
            if sig and cl["size"] and sig != cl["size"]:
                continue
            cl["members"].append(name)
            if sig and not cl["size"]:
                cl["size"] = sig
            placed = True
            break
        if not placed:
            clusters.append({"norm": norm, "size": sig, "members": [name]})

    for cl in clusters:
        max_id += 1
        members = cl["members"]
        canonical = _clean_display(max(members, key=lambda n: counts[n]))
        for name in members:
            mapping[name] = (canonical, max_id)
        canon_by_norm.setdefault(cl["norm"], (canonical, max_id))
        norm_keys.append(cl["norm"])

    return mapping


def load_mapping(path: Path = MAPPING_CSV) -> Dict[str, Tuple[str, int]]:
    if not path.exists():
        return {}
    out: Dict[str, Tuple[str, int]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["raw_name"]] = (row["canonical_name"], int(row["product_id"]))
    return out


def save_mapping(mapping: Dict[str, Tuple[str, int]], path: Path = MAPPING_CSV) -> None:
    rows = sorted(mapping.items(), key=lambda kv: (kv[1][1], kv[0]))
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["raw_name", "canonical_name", "product_id"])
        for raw, (canonical, pid) in rows:
            w.writerow([raw, canonical, pid])
