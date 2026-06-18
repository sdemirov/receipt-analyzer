"""Rename receipt PDFs to their purchase date: YYYY-MM-DD.pdf

The date is read from the receipt body (the `Дата:` line), not the existing
filename. Receipts that share a day are disambiguated by purchase time:
the earliest keeps `YYYY-MM-DD.pdf`, later ones get `_2`, `_3`, ...

Safe by design:
- dry-run by default; pass --apply to actually rename;
- idempotent (already-correct names are left alone);
- two-phase rename via temp names so a file is never clobbered.

Run from the project root:
    venv/Scripts/python.exe -m tools.rename_pdfs            # preview
    venv/Scripts/python.exe -m tools.rename_pdfs --apply    # do it
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from config import RECEIPTS_DIR
from extract.parse import parse_receipt

TEMP_SUFFIX = ".tmprename"


def build_plan():
    """Return [(path, new_name, unp)] and a list of duplicate UNPs."""
    rows = []
    for p in sorted(RECEIPTS_DIR.glob("*.pdf")):
        r = parse_receipt(p)
        rows.append((p, r.purchase_date, r.purchase_time or "", r.unp))

    # Deterministic order: by date, then time, then current name.
    rows.sort(key=lambda x: (x[1] or "9999-99-99", x[2], x[0].name))

    counter = defaultdict(int)
    seen_unp, duplicate_unp = set(), []
    plan = []
    for path, date, _time, unp in rows:
        if unp in seen_unp:
            duplicate_unp.append((path, unp))
        else:
            seen_unp.add(unp)
        if not date:
            new_name = path.name  # leave unchanged if no date found
        else:
            counter[date] += 1
            n = counter[date]
            new_name = f"{date}.pdf" if n == 1 else f"{date}_{n}.pdf"
        plan.append((path, new_name, unp))
    return plan, duplicate_unp


def main(apply: bool) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    plan, duplicate_unp = build_plan()

    changes = [(p, t) for p, t, _ in plan if p.name != t]
    print(f"Folder: {RECEIPTS_DIR}")
    print(f"{len(plan)} PDFs · {len(changes)} to rename · "
          f"{len(plan) - len(changes)} already correct · "
          f"{len(duplicate_unp)} duplicate receipt(s)\n")

    for p, t, _ in plan:
        mark = "->" if p.name != t else "=="
        print(f"  {p.name:30} {mark} {t}")

    if duplicate_unp:
        print("\nDuplicate receipts (same UNP, different file) — kept, just suffixed:")
        for p, unp in duplicate_unp:
            print(f"  {p.name}  (UNP {unp})")

    if not apply:
        print("\n(dry run — re-run with --apply to rename)")
        return

    # Phase 1: move every changing file to a unique temp name.
    staged = []
    for p, t in changes:
        tmp = p.with_name(t + TEMP_SUFFIX)
        p.rename(tmp)
        staged.append((tmp, p.with_name(t)))
    # Phase 2: temp -> final.
    for tmp, final in staged:
        tmp.rename(final)

    print(f"\nDone: renamed {len(changes)} files.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform the rename")
    main(ap.parse_args().apply)
